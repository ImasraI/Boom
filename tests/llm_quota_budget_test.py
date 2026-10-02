"""Provider-quota budget: batched answer verification + pool provider failover.

Context: the pool could not build a single booklet on Gemini's free tier
(20 requests/day/model). Two independent reasons, both fixed here:

  1. The verifier made ONE solver call PER QUESTION, so a 105-question
     ریاضی فیزیک booklet cost ~108 requests (3 generation + 105 verification)
     plus repairs. Batching (10 questions/call) brings the same booklet to
     ~14 requests - the difference between "impossible on any free tier" and
     ~50 booklets/day on Groq's.
  2. A per-day quota is per provider, and it cannot clear inside a request, so
     one exhausted free tier stopped the whole pool. With
     POOL_LLM_FALLBACK_PROVIDERS the pool continues on the next provider - and
     ONLY on a per-day exhaustion, never on a transient per-minute limit.

The safety rule both changes must preserve: an unverified answer key never
reaches a student. A refused call drops questions (fail closed), it never
marks them verified.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import pytest

from app.rag import llm as llm_mod
from app.rag import mock_generation as mg
from app.rag.llm import (BaseLLMClient, FallbackLLMClient, GroqLLMClient,
                         MockLLMClient, get_pool_llm_client)


# --------------------------------------------------------------------------
# Batched verification
# --------------------------------------------------------------------------

DAILY_QUOTA = ("HTTP 429 (You exceeded your current quota | "
               "GenerateRequestsPerDayPerProjectPerModel-FreeTier)")


def _question(i, answer=0):
    return {"_id": i, "subject": "ریاضی", "topic": "", "text": f"سوال {i}",
            "options": ["الف", "ب", "ج", "د"], "answer": answer,
            "explanation": ""}


class CountingSolver:
    """A fake solver: counts calls and answers from a scripted plan.

    `correct` answers match the stored key, `wrong` answer a different option,
    `unsolvable` returns null. Anything past the scripted list is answered
    correctly, so a full-agreement run is the default.
    """

    def __init__(self, script=None, reply=None, empty_after=None, single=0):
        self.calls = 0
        self.batches = []
        self.script = list(script or [])
        self.reply = reply
        self.empty_after = empty_after
        self.last_error = ""
        # Index this solver "computes" for the single-question template (used
        # when it re-verifies a replacement question).
        self.single = single

    def generate(self, messages, max_tokens=None, timeout=None, images=None):
        self.calls += 1
        prompt = messages[-1]["content"]
        self.batches.append(prompt)
        if self.empty_after is not None and self.calls > self.empty_after:
            self.last_error = DAILY_QUOTA
            return ""
        if self.reply is not None:
            return self.reply
        # Recover the questions from the prompt: "[n]\nمتن سوال: ..."
        numbers = [int(m) for m in __import__("re").findall(r"\[(\d+)\]", prompt)]
        if not numbers:
            # Not a batch prompt: the one-question template `_verify_question`
            # uses for replacements.
            return json.dumps({"answer": self.single})
        answers = {}
        for pos in numbers:
            mode = self.script[pos - 1] if pos - 1 < len(self.script) else "correct"
            if mode == "unsolvable":
                answers[str(pos)] = None
            elif mode == "wrong":
                answers[str(pos)] = 1  # stored keys are 0
            else:
                answers[str(pos)] = 0
        return json.dumps({"answers": answers})


def _patch_solver(monkeypatch, solver):
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: solver)
    return solver


def test_a_full_booklet_costs_one_solver_call_per_batch_not_per_question(monkeypatch):
    """105 questions must cost 11 solver calls, not 105."""
    questions = [_question(i) for i in range(1, 106)]
    solver = _patch_solver(monkeypatch, CountingSolver())
    out = mg.verify_and_repair_booklet(questions, 1, timeout=10)
    assert len(out) == 105
    assert solver.calls == 11  # ceil(105 / 10)
    assert all(q["verification_status"] == "verified" for q in out)


def test_batch_size_is_respected_for_a_short_booklet(monkeypatch):
    solver = _patch_solver(monkeypatch, CountingSolver())
    mg.verify_and_repair_booklet([_question(i) for i in range(1, 6)], 1, timeout=10)
    assert solver.calls == 1


def test_wrong_keys_are_repaired_and_never_kept(monkeypatch):
    """A batch where question 3 disagrees: it must be replaced, re-verified,
    and only then kept - and the answer key must come from the replacement."""
    questions = [_question(i) for i in range(1, 4)]
    solver = CountingSolver(script=["correct", "correct", "wrong"])
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: solver)
    fresh = _question(1, answer=0)
    fresh["text"] = "سوال جایگزین"
    monkeypatch.setattr(mg, "_generate_replacement", lambda *a, **k: fresh)
    out = mg.verify_and_repair_booklet(questions, 1, max_regens=1, timeout=10)
    texts = [q["text"] for q in out]
    assert texts == ["سوال 1", "سوال 2", "سوال جایگزین"]
    # The kept question is the replacement's, with the replacement's own key.
    assert out[2]["verification_status"] == "verified"
    assert out[2]["answer"] == 0
    assert out[2]["_id"] == 3 and out[2]["subject"] == "ریاضی"


def test_unsolvable_questions_are_not_marked_verified(monkeypatch):
    """null / an unclean reply means \"could not verify\", never a guess."""
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: CountingSolver(
        script=["unsolvable"]))
    monkeypatch.setattr(mg, "_generate_replacement", lambda *a, **k: None)
    assert mg.verify_and_repair_booklet([_question(1)], 1, max_regens=1) == []


def test_a_refused_call_stops_after_one_request(monkeypatch):
    """A per-day quota must cost ONE request, not one per question.

    The questions verified before the refusal are kept; everything after it is
    dropped, so the pool sees a short booklet (and discards it) instead of
    storing unverified keys.
    """
    questions = [_question(i) for i in range(1, 106)]
    solver = CountingSolver(empty_after=1)  # first batch answers, then refusal
    _patch_solver(monkeypatch, solver)
    events = []
    out = mg.verify_and_repair_booklet(questions, 1, timeout=10,
                                       report=lambda e, d: events.append((e, d)))
    assert solver.calls == 2, "must stop at the first refused batch"
    assert len(out) == 10, "only the first batch was verified"
    assert all(q["verification_status"] == "verified" for q in out)
    assert any(e == "provider_error" for e, _ in events)
    assert any("GenerateRequestsPerDay" in str(d.get("message", ""))
               for e, d in events if e == "provider_error")


def test_fail_closed_also_when_the_first_batch_is_refused(monkeypatch):
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: CountingSolver(
        empty_after=0))
    assert mg.verify_and_repair_booklet([_question(1)], 1, timeout=10) == []


# ------------------------------------------------- parser strictness ---

def test_batch_parser_only_accepts_clean_indices():
    parsed = mg._parse_batch_answers(
        '{"answers": {"1": 2, "2": null, "3": "3", "4": true, "5": 4,'
        ' "6": "x", "7": 1.5, "99": 0}}', 7)
    assert parsed == {1: 2, 2: None, 3: 3, 4: None, 5: None, 6: None, 7: None}


def test_batch_parser_handles_persian_digits_and_prose_and_junk():
    assert mg._parse_batch_answers('{"answers": {"۱": 1, "۲": 0}}', 2) == {1: 1, 2: 0}
    assert mg._parse_batch_answers('نتیجه: {"1": 0, "2": 1,} پایان', 2) == {1: 0, 2: 1}
    assert mg._parse_batch_answers("not json at all", 2) == {1: None, 2: None}
    assert mg._parse_batch_answers("", 2) == {1: None, 2: None}
    # A bare {n: idx} object (no "answers" wrapper) is accepted too.
    assert mg._parse_batch_answers('{"1": 3}', 1) == {1: 3}


def test_batch_prompt_numbers_every_question_and_shows_no_answers():
    prompt = mg._verify_batch_prompt([_question(1), _question(2)])
    assert "[1]" in prompt and "[2]" in prompt
    assert prompt.count("الف") == 2
    # No stored key may leak into the solver's prompt.
    assert '"answer":' not in prompt


# --------------------------------------------------------------------------
# Pool provider failover
# --------------------------------------------------------------------------

class FakeClient(BaseLLMClient):
    """A provider stub: fixed reply + its own last_error."""

    def __init__(self, reply="پاسخ", error=""):
        self.reply = reply
        self.error = error
        self.calls = 0

    def generate(self, messages, max_tokens=None, timeout=None, images=None):
        self.calls += 1
        self.last_error = "" if self.reply else self.error
        return self.reply

    def generate_stream(self, messages, images=None):
        yield self.reply


def test_failover_continues_on_the_next_provider_after_a_daily_quota():
    dead = FakeClient(reply="", error=DAILY_QUOTA)
    alive = FakeClient(reply="سوال ساخته شد")
    client = FallbackLLMClient([dead, alive], ["gemini", "groq"])
    assert client.generate([{"role": "user", "content": "p"}]) == "سوال ساخته شد"
    assert dead.calls == 1 and alive.calls == 1
    # The switch is sticky: the next call goes straight to the live provider.
    assert client.generate([{"role": "user", "content": "p"}]) == "سوال ساخته شد"
    assert dead.calls == 1 and alive.calls == 2
    assert client.active_label == "groq"


def test_failover_ignores_transient_failures():
    """A per-minute limit or a timeout must NOT spend another key's quota."""
    busy = FakeClient(reply="", error="HTTP 429 (rate limit per minute)")
    backup = FakeClient(reply="سوال")
    client = FallbackLLMClient([busy, backup], ["gemini", "groq"])
    assert client.generate([{"role": "user", "content": "p"}]) == ""
    assert backup.calls == 0
    assert client.active_label == "gemini"
    assert "rate limit per minute" in client.last_error


def test_last_error_reports_the_provider_that_actually_gave_up():
    dead = FakeClient(reply="", error=DAILY_QUOTA)
    also_dead = FakeClient(reply="", error=DAILY_QUOTA + " (second)")
    client = FallbackLLMClient([dead, also_dead], ["gemini", "groq"])
    assert client.generate([{"role": "user", "content": "p"}]) == ""
    assert "second" in client.last_error


# ------------------------------------------------------ factory wiring ---

def _settings(**over):
    base = dict(
        LLM_PROVIDER="groq",
        LLM_API_KEY="main-key",
        LLM_MODEL_NAME="main-model",
        LLM_TEMPERATURE=0.2,
        LLM_MAX_TOKENS=100,
        LLM_BASE_URL="https://api.groq.com/openai/v1",
        GEMINI_API_KEY="g-key",
        GEMINI_MODEL_NAME="gemini-model",
        GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai",
        GEMINI_PROXY="",
        CEREBRAS_API_KEY="c-key",
        CEREBRAS_MODEL_NAME="c-model",
        CEREBRAS_BASE_URL="https://api.cerebras.ai/v1",
        POOL_LLM_API_KEY="",
        POOL_LLM_MODEL_NAME="",
        POOL_LLM_PROVIDER="",
        POOL_LLM_FALLBACK_PROVIDERS="",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_no_fallback_configured_returns_the_plain_primary_client(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings())
    client = get_pool_llm_client()
    assert isinstance(client, GroqLLMClient)


def test_fallback_chain_is_built_from_config(monkeypatch):
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_PROVIDER="gemini",
        POOL_LLM_FALLBACK_PROVIDERS="groq, cerebras"))
    client = get_pool_llm_client()
    assert isinstance(client, FallbackLLMClient)
    assert [type(c).__name__ for c in client._clients] == \
        ["GeminiLLMClient", "GroqLLMClient", "CerebrasLLMClient"]
    assert client._labels == ["gemini", "groq", "cerebras"]


def test_fallback_skips_the_primary_and_keyless_providers(monkeypatch):
    """A duplicate provider is the same quota, and a provider with no key
    would only generate nothing forever - both are skipped."""
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_PROVIDER="gemini",
        GEMINI_API_KEY="",
        CEREBRAS_API_KEY="",
        POOL_LLM_FALLBACK_PROVIDERS="gemini, cerebras, groq"))
    client = get_pool_llm_client()
    assert isinstance(client, FallbackLLMClient)
    assert client._labels == ["gemini", "groq"]


def test_fallback_chain_is_one_client_short_of_a_wrapper(monkeypatch):
    """Only unusable fallbacks configured -> the primary is returned as-is."""
    monkeypatch.setattr(llm_mod, "get_settings", lambda: _settings(
        POOL_LLM_PROVIDER="groq",
        GEMINI_API_KEY="",
        POOL_LLM_FALLBACK_PROVIDERS="groq, gemini"))
    client = get_pool_llm_client()
    assert isinstance(client, GroqLLMClient)
    assert not isinstance(client, FallbackLLMClient)


def test_mock_client_has_no_failover_side_effects():
    """The wrapper never fabricates an answer when every provider is down."""
    dead_a = FakeClient(reply="", error=DAILY_QUOTA)
    dead_b = FakeClient(reply="", error=DAILY_QUOTA)
    client = FallbackLLMClient([dead_a, dead_b], ["gemini", "groq"])
    assert client.generate([{"role": "user", "content": "p"}]) == ""
    assert isinstance(MockLLMClient(), BaseLLMClient)
