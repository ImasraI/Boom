"""Groq drafts and repairs; independent Gemini checks never see stored keys."""
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.rag import llm, mock_generation as mg, provider_quota as quota, pool_pacing


def configuration(**overrides):
    values = dict(LLM_PROVIDER="groq", LLM_API_KEY="chat-secret", LLM_MODEL_NAME="chat-model",
        LLM_BASE_URL="https://api.groq.com/openai/v1", LLM_TEMPERATURE=0.2, LLM_MAX_TOKENS=1600,
        POOL_LLM_PROVIDER="groq", POOL_LLM_API_KEY="groq-pool-secret",
        POOL_LLM_MODEL_NAME="openai/gpt-oss-120b", POOL_LLM_FALLBACK_PROVIDERS="",
        POOL_GEMINI_API_KEYS="old-backup-secret", POOL_VERIFY_LLM_PROVIDER="gemini",
        POOL_VERIFY_LLM_API_KEY="gemini-verify-secret", POOL_VERIFY_LLM_MODEL_NAME="gemini-3.6-flash",
        POOL_VERIFY_GEMINI_API_KEYS="gemini-verify-backup", POOL_VERIFY_MAX_TOKENS=2400,
        POOL_VERIFY_REASONING_EFFORT="low", GEMINI_API_KEY="vision-secret",
        GEMINI_MODEL_NAME="gemini-vision-model", GEMINI_PROXY="",
        GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai",
        POOL_GENERATION_BATCH_SIZE=2, POOL_GENERATION_MAX_TOKENS=2400,
        POOL_GENERATION_CONTEXT_CHARS=1800, POOL_GENERATION_REQUESTS_PER_MINUTE=0)
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    config = configuration()
    import app.config
    monkeypatch.setattr(app.config, "get_settings", lambda: config)
    monkeypatch.setattr(llm, "get_settings", lambda: config)
    monkeypatch.setattr(mg, "get_settings", lambda: config)
    monkeypatch.setattr(quota, "_state_file", lambda: None)
    quota._BLOCKS.clear(); quota._LOADED_PATHS.clear(); pool_pacing._NEXT_START.clear()
    yield config
    quota._BLOCKS.clear(); quota._LOADED_PATHS.clear(); pool_pacing._NEXT_START.clear()


class Replies:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.prompts = []
        self.budgets = []
        self.last_error = ""

    def generate(self, messages, max_tokens=None, **kwargs):
        self.prompts.append(messages[-1]["content"])
        self.budgets.append(max_tokens)
        reply = next(self.replies)
        if not reply:
            self.last_error = "HTTP 429 daily quota exhausted"
        return reply


def question(number=1, answer=0):
    return {"_id":number, "text":f"سوال مستقل {number}", "subject":"ریاضی", "topic":"تابع",
            "options":["الف","ب","ج","د"], "answer":answer,
            "explanation":"PRIVATE_GENERATOR_EXPLANATION"}


def test_factories_separate_credentials_models_and_reasoning(isolated_settings):
    draft = llm.get_pool_llm_client()
    verifier = llm.get_pool_verifier_client()
    assert isinstance(draft, llm.GroqLLMClient)
    assert draft.model == "openai/gpt-oss-120b"
    assert draft.client.headers["Authorization"] == "Bearer groq-pool-secret"
    assert isinstance(verifier, llm.FallbackLLMClient)
    assert [c.model for c in verifier._clients] == ["gemini-3.6-flash"]*2
    assert [c.client.headers["Authorization"] for c in verifier._clients] == [
        "Bearer gemini-verify-secret","Bearer gemini-verify-backup"]
    payload = verifier.active._prepare_payload([], max_tokens=200)
    assert payload["reasoning_effort"] == "low" and payload["max_tokens"] == 2400
    assert payload["temperature"] == 0.0
    draft.client.close()
    for child in verifier._clients:
        child.client.close()


def test_checks_and_replacement_checks_use_verifier_only(monkeypatch):
    verifier = Replies(['{"answers":{"1":1}}', '{"answer":2}'])
    fresh = question(2, answer=2)
    fresh["text"] = "سوال جایگزین مستقل"
    drafter = Replies([json.dumps({"questions":[fresh]})])
    monkeypatch.setattr(mg, "get_pool_verifier_client", lambda: verifier)
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: drafter)
    monkeypatch.setattr(mg, "retrieve_book_context", lambda *a, **k:"book excerpt")
    out = mg.verify_and_repair_booklet([question()], 7, max_regens=1)
    assert len(out)==1 and out[0]["answer"]==2 and out[0]["_id"]==1
    assert out[0]["verification_status"]=="verified"
    assert len(drafter.prompts)==1 and len(verifier.prompts)==2
    assert all("PRIVATE_GENERATOR_EXPLANATION" not in p for p in verifier.prompts)
    assert '"answer":' not in verifier.prompts[0]


def test_accepted_questions_never_create_a_drafting_client(monkeypatch):
    monkeypatch.setattr(mg, "get_pool_verifier_client", lambda: Replies(['{"answers":{"1":0}}']))
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: pytest.fail("No repair should be drafted"))
    assert len(mg.verify_and_repair_booklet([question()], 7))==1


def test_verifier_daily_limit_preserves_only_previously_checked_questions(monkeypatch):
    verifier = Replies(['{"answers":{"1":0}}', ''])
    monkeypatch.setattr(mg, "get_pool_verifier_client", lambda: verifier)
    monkeypatch.setattr(mg, "get_pool_llm_client", lambda: pytest.fail("Must not use drafting as verification fallback"))
    monkeypatch.setattr(mg, "_VERIFY_BATCH_SIZE", 1)
    out = mg.verify_and_repair_booklet([question(1),question(2)], 7)
    assert [q["_id"] for q in out]==[1]


def test_blocked_verifier_stops_restock_before_groq_is_spent(isolated_settings):
    config = isolated_settings
    for key in quota.pool_gemini_keys(config, verification=True):
        quota.block_daily_quota(quota.quota_identity(config.GEMINI_BASE_URL,
            config.POOL_VERIFY_LLM_MODEL_NAME,key), "daily quota")
    status = quota.pool_quota_status()
    assert status["blocked"] and status["stage"]=="verification"
    assert status["code"]=="provider_daily_quota"
    with pytest.raises(HTTPException) as exc:
        quota.require_pool_available()
    assert exc.value.status_code==503 and exc.value.headers.get("Retry-After")


def test_available_verifier_backup_unblocks_pipeline(isolated_settings):
    config = isolated_settings
    quota.block_daily_quota(quota.quota_identity(config.GEMINI_BASE_URL,
        config.POOL_VERIFY_LLM_MODEL_NAME,config.POOL_VERIFY_LLM_API_KEY),"daily quota")
    assert not quota.pool_quota_status()["blocked"]


def test_missing_verifier_key_is_reported_before_drafting(isolated_settings):
    isolated_settings.POOL_VERIFY_LLM_API_KEY = ""
    isolated_settings.POOL_VERIFY_GEMINI_API_KEYS = ""
    isolated_settings.GEMINI_API_KEY = ""
    with pytest.raises(HTTPException) as exc:
        quota.require_pool_available()
    assert exc.value.status_code==503 and exc.value.detail["code"]=="provider_not_configured"


def test_rejected_verifier_blocks_drafting_and_keeps_accepted_questions(monkeypatch,isolated_settings):
    config=isolated_settings
    for key in quota.pool_gemini_keys(config,verification=True):
        quota.block_access(quota.quota_identity(config.GEMINI_BASE_URL,config.POOL_VERIFY_LLM_MODEL_NAME,key),401)
    status=quota.pool_quota_status()
    assert status['blocked'] and status['stage']=='verification' and status['code']=='provider_access_denied'
    solver=Replies(['{"answers":{"1":0}}',''])
    def refusal(messages,**kwargs):
        solver.last_error='HTTP 401'
        return ''
    monkeypatch.setattr(mg,'get_pool_verifier_client',lambda:solver)
    monkeypatch.setattr(mg,'get_pool_llm_client',lambda:pytest.fail('Rejected verification must not spend Groq on repairs'))
    monkeypatch.setattr(mg,'_VERIFY_BATCH_SIZE',1)
    original=solver.generate
    solver.generate=lambda messages,**kwargs: original(messages,**kwargs) if not solver.prompts else refusal(messages,**kwargs)
    out=mg.verify_and_repair_booklet([question(1),question(2)],7)
    assert [q['_id'] for q in out]==[1]


def test_batched_drafts_retrieve_once_and_preserve_grade_and_subject(monkeypatch):
    calls=[]
    drafter=Replies([json.dumps({"questions":[question(i) for i in ids]})
                      for ids in ((1,2),(3,4),(5,))])
    monkeypatch.setattr(mg,"retrieve_book_context",lambda *a,**k:calls.append(a) or "C"*3000)
    monkeypatch.setattr(mg,"get_pool_llm_client",lambda:drafter)
    out=mg.generate_booklet(7,[{"name":"شیمی","questions":5,"minutes":10}],
                           ["تعادل"],"konkur",6000,60,grade="یازدهم")
    assert len(out)==5 and len(calls)==1 and len(drafter.prompts)==3
    assert all(q["subject"]=="شیمی" for q in out)
    assert all("یازدهم" in p and "تعادل" in p for p in drafter.prompts)
    assert [q["_id"] for q in out]==list(range(1,6))
    assert drafter.budgets==[2400]*3
    assert "C"*1800 in drafter.prompts[0] and "C"*1801 not in drafter.prompts[0]
    assert "سوال مستقل 1" in drafter.prompts[1]


def test_daily_draft_failure_stops_remaining_batches(monkeypatch):
    drafter=Replies([json.dumps({"questions":[question(1),question(2)]}), ''])
    monkeypatch.setattr(mg,"retrieve_book_context",lambda *a,**k:"source")
    monkeypatch.setattr(mg,"get_pool_llm_client",lambda:drafter)
    out = mg._generate_subject_questions(7,{"name":"ریاضی","questions":8},[],"konkur",6000,60)
    assert [q['text'] for q in out] == ['سوال مستقل 1', 'سوال مستقل 2']
    assert all(q.get('verification_status') != 'verified' for q in out)
    assert len(drafter.prompts)==2


def test_draft_quota_preserves_finished_subjects_for_independent_verification(monkeypatch):
    drafter = Replies([json.dumps({'questions':[question(1), question(2)]}), ''])
    solver = Replies(['{"answers":{"1":0,"2":0}}'])
    monkeypatch.setattr(mg, 'retrieve_book_context', lambda *a, **k:'source')
    monkeypatch.setattr(mg, 'get_pool_llm_client', lambda:drafter)
    monkeypatch.setattr(mg, 'get_pool_verifier_client', lambda:solver)
    monkeypatch.setattr(mg, 'pad_booklet', lambda rows: rows)  # Keep deterministic option positions.
    harvested = []
    plan = [{'name':'ریاضی','questions':2,'minutes':2},
            {'name':'فیزیک','questions':2,'minutes':2},
            {'name':'شیمی','questions':2,'minutes':2}]
    kept, _, _ = mg.build_pool_booklet('riazi', plan=plan, on_verified=harvested.extend)
    assert kept == []  # Incomplete papers never become ready mocks.
    assert len(drafter.prompts) == 2 and len(solver.prompts) == 1
    assert len(harvested) == 2 and all(q['verification_status']=='verified' for q in harvested)


def test_failed_repair_keeps_other_independent_batch_verdicts(monkeypatch):
    solver = Replies(['{"answers":{"1":1,"2":0,"3":0}}'])
    drafter = Replies([''])
    monkeypatch.setattr(mg, 'retrieve_book_context', lambda *a, **k:'source')
    monkeypatch.setattr(mg, 'get_pool_llm_client', lambda:drafter)
    monkeypatch.setattr(mg, 'get_pool_verifier_client', lambda:solver)
    out = mg.verify_and_repair_booklet([question(1),question(2),question(3)],0)
    assert [q['_id'] for q in out] == [2,3]
    assert len(drafter.prompts) == 1 and len(solver.prompts) == 1


def test_daily_limit_during_short_batch_retry_keeps_parseable_candidates(monkeypatch):
    drafter = Replies([json.dumps({'questions':[question(1)]}), ''])
    monkeypatch.setattr(mg,'get_settings',lambda:configuration(POOL_GENERATION_BATCH_SIZE=4))
    monkeypatch.setattr(mg,'retrieve_book_context',lambda *a,**k:'source')
    monkeypatch.setattr(mg,'get_pool_llm_client',lambda:drafter)
    out = mg.generate_booklet(0,[{'name':'ریاضی','questions':4,'minutes':4}])
    assert len(out) == 1 and len(drafter.prompts) == 2
    assert out[0].get('verification_status') != 'verified'


def test_solver_receives_chart_data_without_generator_metadata(monkeypatch):
    q=question()
    q["figure"]={"type":"bar_chart","data":{"categories":["A","B"],"values":[12,19]}}
    solver=Replies(['{"answer":0}'])
    assert mg._verify_question(solver,q,30)==0
    for prompt in [solver.prompts[0],mg._verify_batch_prompt([q])]:
        assert "bar_chart" in prompt and "19" in prompt
        assert "PRIVATE_GENERATOR_EXPLANATION" not in prompt


def test_missing_table_is_repaired_even_when_solver_guesses_stated_answer(monkeypatch):
    bad=question()
    bad['text']='در جدول زیر، ترکیب X کدام است؟'
    bad['figure']={'type':'none','data':{}}
    fresh=question(2)
    fresh['text']='یک سوال کامل بدون جدول'
    solver=Replies(['{"answers":{"1":0}}','{"answer":0}'])
    drafter=Replies([json.dumps({'questions':[fresh]})])
    monkeypatch.setattr(mg,'get_pool_verifier_client',lambda:solver)
    monkeypatch.setattr(mg,'get_pool_llm_client',lambda:drafter)
    monkeypatch.setattr(mg,'retrieve_book_context',lambda *a,**kw:'source')
    out=mg.verify_and_repair_booklet([bad],7,max_regens=1)
    assert len(out)==1 and out[0]['text']==fresh['text'] and len(drafter.prompts)==1


def test_missing_diagram_never_spends_a_single_solver_call():
    bad=question()
    bad['text']='مطابق نمودار زیر، سرعت چند است؟'
    solver=Replies([])
    assert mg._verify_question(solver,bad,30) is None and not solver.prompts


def test_supplied_chart_and_inline_table_are_not_rejected_as_missing():
    q=question()
    q['text']='مطابق نمودار زیر، کدام مقدار بیشتر است؟'
    q['figure']={'type':'bar_chart','data':{'categories':['A','B'],'values':[1,2]}}
    assert not mg._missing_visible_reference(q)
    q['text']='جدول زیر را ببینید:\n| x | y |\n|---|---|\n|1|2|'
    q['figure']={'type':'none','data':{}}
    assert not mg._missing_visible_reference(q)


def test_pacing_is_shared_by_new_clients_but_not_other_credentials(monkeypatch):
    waits=[]
    monkeypatch.setattr(pool_pacing.time,"monotonic",lambda:100.0)
    monkeypatch.setattr(pool_pacing.time,"sleep",waits.append)
    pool_pacing.wait_for_draft_slot("same-pool",1)
    pool_pacing.wait_for_draft_slot("same-pool",1)
    pool_pacing.wait_for_draft_slot("another-pool",1)
    assert waits==[60.0]
    pool_pacing.wait_for_draft_slot("same-pool",0)
    assert waits==[60.0]


def test_unconfigured_verifier_keeps_legacy_factory(isolated_settings):
    isolated_settings.POOL_VERIFY_LLM_PROVIDER=""
    client=llm.get_pool_verifier_client()
    assert isinstance(client,llm.GroqLLMClient)
    client.client.close()
