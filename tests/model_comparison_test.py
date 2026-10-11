import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("compare_mock_models", Path(__file__).parents[1] / "backend/scripts/compare_mock_models.py")
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def test_comparison_uses_exact_20_book_backed_slots(monkeypatch):
    def lessons(row, grade):
        return [{"id": row["name"] + row["branch"] + str(i), "title": "درس" + str(i), "subject": row["name"]} for i in range(10)]
    monkeypatch.setattr(comparison.blueprint, "lessons_for", lessons)
    monkeypatch.setattr(comparison.blueprint, "book_excerpt", lambda node, limit: {"book": "کتاب", "page": 42, "quote": "متن واقعی کتاب"})
    slots = comparison.prepare_slots()
    assert slots == comparison.prepare_slots()  # fixed topics across providers/resumes
    assert len(slots) == 20
    assert {s: sum(q["subject"] == s for q in slots) for s in ["ریاضی", "فیزیک", "شیمی"]} == {"ریاضی": 7, "فیزیک": 7, "شیمی": 6}
    assert all(q["source"]["quote"] for q in slots)
    prompt = comparison.draft_prompt(slots[0], "hard")
    assert "متن واقعی کتاب" in prompt and slots[0]["node"]["title"] in prompt


def test_gemini_comparison_never_receives_primary_groq_key(monkeypatch):
    config = SimpleNamespace(POOL_LLM_PROVIDER="groq", POOL_LLM_API_KEY="groq-private",
        POOL_GEMINI_API_KEYS="google-a,google-b,google-a", POOL_VERIFY_LLM_MODEL_NAME="gemini-3.6-flash")
    created = []
    def client(**kwargs):
        created.append(kwargs)
        return SimpleNamespace()
    monkeypatch.setattr(comparison, "get_llm_client", client)
    fleet, model = comparison.fleet("gemini", config)
    assert {c['api_key'] for c in created} == {"google-a", "google-b"}
    assert all(c['provider'] == 'gemini' and c['model'] == model for c in created)
    assert all(c.reasoning_effort == 'high' and c.minimum_completion_tokens == 8192 for c in fleet._clients)


def test_comparison_can_use_configured_same_model_reviewer_fleet(monkeypatch):
    config = SimpleNamespace(POOL_LLM_PROVIDER="groq", POOL_LLM_API_KEY="groq-private",
        POOL_GEMINI_API_KEYS="google-a", POOL_VERIFY_LLM_MODEL_NAME="gemini-3.6-flash",
        POOL_VERIFY_LLM_PROVIDER="gemini")
    monkeypatch.setattr(comparison.quota, "pool_gemini_keys", lambda settings, verification: ["google-b"])
    created = []
    monkeypatch.setattr(comparison, "get_llm_client", lambda **kwargs: created.append(kwargs) or SimpleNamespace())
    comparison.fleet("gemini", config)
    assert [c['api_key'] for c in created] == ['google-a', 'google-b']


def test_busy_provider_saves_retry_and_does_not_invent_a_question(tmp_path, monkeypatch):
    import time
    client = SimpleNamespace(_clients=[], last_error="HTTP 503 temporary high demand", last_error_code="",
        generate=lambda *a, **kw: "")
    monkeypatch.setattr(comparison, "fleet", lambda provider, settings: (client, "gemini-test"))
    monkeypatch.setattr(comparison, "available", lambda c: True)
    monkeypatch.setattr(comparison, "draft_prompt", lambda slot, difficulty: "JSON prompt")
    state = {"slots": [{}], "models": {}, "difficulty": "hard"}
    comparison.run_model("gemini", state, tmp_path / "state.json", True)
    result = state['models']['gemini']
    assert result['status'] == 'waiting_for_provider' and result['questions'] == []
    assert result['last_error_code'] == 'http_503' and result['retry_at'] > time.time()


def test_rejected_request_stops_instead_of_repeatedly_spending_quota(tmp_path, monkeypatch):
    calls = []
    def generate(*a, **kw):calls.append(1);return ""
    client = SimpleNamespace(_clients=[], last_error="HTTP 413", last_error_code="", generate=generate)
    monkeypatch.setattr(comparison, "fleet", lambda provider, settings: (client, "groq-test"))
    monkeypatch.setattr(comparison, "available", lambda c: True)
    monkeypatch.setattr(comparison, "draft_prompt", lambda slot, difficulty: "JSON prompt")
    state = {"slots": [{}], "models": {}, "difficulty": "hard"}
    comparison.run_model("groq", state, tmp_path / "state.json", False)
    assert state['models']['groq']['status'] == 'needs_attention_request' and calls == [1]
