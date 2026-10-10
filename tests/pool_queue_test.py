import json
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, func, select

from app.config import Settings
from app.auth.database import PoolDraftJob, BankQuestion, GeneratedMock, SessionLocal
from app.rag import pool_queue as queue, pool_service, pool_core, provider_quota, llm


def config():
    return dict(kind="mock", majors=["riazi"], difficulties=["konkur"], grade="دوازدهم",
                count=0, total_questions=5, subjects=["ریاضی"], topics=["تابع"])


@pytest.fixture
def setup(monkeypatch):
    settings = Settings(_env_file=None, POOL_DRAFT_QUEUE_ENABLED=True, POOL_DRAFT_QUEUE_CAPACITY=2,
        POOL_LLM_PROVIDER="groq", POOL_LLM_API_KEY="draft-key", LLM_API_KEY="",
        POOL_GROQ_API_KEYS="backup-key", POOL_VERIFY_LLM_PROVIDER="gemini",
        POOL_VERIFY_LLM_API_KEY="verifier-key", GEMINI_API_KEY="",
        POOL_VERIFY_GEMINI_API_KEYS="", POOL_VERIFY_GROQ_API_KEYS="", POOL_GEMINI_API_KEYS="",
        POOL_VERIFY_FALLBACK_PROVIDERS="groq", POOL_VERIFY_GROQ_USE_POOL_KEYS=True)
    monkeypatch.setattr(queue, "get_settings", lambda: settings)
    pool_service._shutdown.clear()
    pool_core.finish_progress(); pool_core.clear_cancel()
    with SessionLocal() as db:
        db.execute(delete(PoolDraftJob)); db.commit()
        bank_before = db.scalar(select(func.max(BankQuestion.id))) or 0
        mock_before = db.scalar(select(func.max(GeneratedMock.id))) or 0
    tag = "queue-qa-" + uuid.uuid4().hex
    yield settings, tag
    with SessionLocal() as db:
        db.execute(delete(PoolDraftJob))
        db.execute(delete(BankQuestion).where(BankQuestion.id > bank_before))
        db.execute(delete(GeneratedMock).where(GeneratedMock.id > mock_before)); db.commit()
    pool_core.finish_progress(); pool_core.clear_cancel()


def question(tag, number=0, answer=0):
    return dict(subject="ریاضی", topic="تابع", text=f"{tag} question {number}",
                options=["1", "2", "3", "4"], answer=answer, explanation="explanation-hidden-from-solver",
                figure={"type": "none", "data": {}}, verification_status="verified", bank_id=999999)


class Solver:
    last_error = ""
    last_error_code = ""
    def __init__(self, answer=0, refused=False):
        self.answer = answer; self.refused = refused; self.prompts = []
    def generate(self, messages, **kwargs):
        self.prompts.append(messages[0]["content"])
        if self.refused:
            self.last_error_code = "provider_daily_quota"
            return ""
        return json.dumps({"answers": {str(i): self.answer for i in range(1, 11)}})


def draft(tag, count=1):
    job_id = queue.create_job(config(), "riazi", "konkur")
    queue.append_batch(job_id, [question(tag, i) for i in range(count)])
    queue.finish_draft(job_id)
    return job_id


def test_pending_candidates_are_durable_private_and_not_bank_stock(setup):
    settings, tag = setup
    job_id = draft(tag, 5)
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        rows = json.loads(job.questions)
        assert job.status == "pending" and job.question_count == 5
        assert all(q["verification_status"] == "pending" and "bank_id" not in q for q in rows)
        assert not db.scalar(select(BankQuestion.id).where(BankQuestion.content.contains(tag)))
    stats = queue.snapshot()
    assert stats["pending_booklets"] == 1 and stats["pending_questions"] == 5


def test_queue_capacity_is_atomic_and_counts_verifying_jobs(setup):
    settings, tag = setup
    draft(tag)
    queue.claim_job()
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: queue.create_job(config(), "riazi", "konkur"), range(3)))
    assert sum(r is not None for r in results) == 1
    assert queue.snapshot()["pending_booklets"] == 2


def test_job_claim_is_exclusive(setup):
    settings, tag = setup
    draft(tag)
    with ThreadPoolExecutor(max_workers=3) as executor:
        claims = list(executor.map(lambda _: queue.claim_job(), range(3)))
    assert sum(c is not None for c in claims) == 1


def test_blind_verification_rejects_disagreement_and_publishes_only_accepted(setup):
    settings, tag = setup
    job_id = draft(tag, 5)
    solver = Solver(answer=0)
    assert queue.claim_job() == job_id
    assert queue.verify_step(job_id, solver)
    assert all("explanation-hidden-from-solver" not in prompt for prompt in solver.prompts)
    with SessionLocal() as db:
        assert db.get(PoolDraftJob, job_id).verified_count == 5
        assert db.get(PoolDraftJob, job_id).status == "completed"
        bank = db.scalars(select(BankQuestion).where(BankQuestion.content.contains(tag))).all()
        assert len(bank) == 5 and all(q.verified for q in bank)
        assert all("_queue_status" not in q.content for q in bank)
    other = draft(tag + "wrong", 1)
    assert queue.claim_job() == other
    assert not queue.verify_step(other, Solver(answer=2))
    with SessionLocal() as db:
        assert db.get(PoolDraftJob, other).status == "rejected"
        assert db.get(PoolDraftJob, other).rejected_count == 1
        assert not db.scalar(select(BankQuestion.id).where(BankQuestion.content.contains(tag + "wrong")))


def test_provider_refusal_preserves_pending_questions_and_prior_verified_batches(setup):
    settings, tag = setup
    job_id = draft(tag, 11)
    queue.claim_job(); queue.verify_step(job_id, Solver())
    queue.claim_job(); assert not queue.verify_step(job_id, Solver(refused=True))
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id)
        assert job.status == "pending" and job.verified_count == 10 and job.rejected_count == 0
        assert job.retry_at > queue._now()
    assert queue.snapshot()["pending_questions"] == 1
    assert queue.claim_job() is None  # Do not immediately repeat a refused call.


def test_restart_recovers_expired_drafting_and_verification_without_losing_questions(setup):
    settings, tag = setup
    job_id = queue.create_job(config(), "riazi", "konkur")
    queue.append_batch(job_id, [question(tag)])
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id); job.lease_until = queue._now() - timedelta(seconds=1); db.commit()
    queue.recover_interrupted()
    assert queue.claim_job() == job_id
    with SessionLocal() as db:
        job = db.get(PoolDraftJob, job_id); job.lease_until = queue._now() - timedelta(seconds=1); db.commit()
    queue.recover_interrupted()
    assert queue.claim_job() == job_id
    queue.verify_step(job_id, Solver())
    assert queue.snapshot()["verified_questions"] == 1


def test_pending_queue_runs_drafting_when_verifier_is_daily_limited(setup, monkeypatch):
    settings, tag = setup
    monkeypatch.setattr(queue, "pool_generation_status", lambda: {"blocked": False, "provider": "groq"})
    monkeypatch.setattr(queue, "pool_verification_status", lambda: {"blocked": True, "provider": "gemini"})
    monkeypatch.setattr(queue, "_assemble", lambda: False)
    calls = []
    def generate(*args, on_drafted, **kwargs):
        calls.append(1); on_drafted([question(tag)])
        pool_service.cancel()
        return []
    monkeypatch.setattr(queue.mock_generation, "generate_booklet", generate)
    pool_service._save({"enabled": True, "status": "starting", "config": config(), "produced": 0, "cursor": 0})
    queue.run()
    assert calls == [1] and queue.snapshot()["pending_questions"] == 1
    assert pool_service.snapshot()["status"] == "stopped"


def test_verified_questions_assemble_into_ready_exact_size_booklet(setup):
    settings, tag = setup
    job_id = draft(tag, 5); queue.claim_job(); queue.verify_step(job_id, Solver())
    cfg = config(); cfg["count"] = 1
    pool_service._save({"enabled": True, "config": cfg, "produced": 0})
    assert queue._assemble()
    assert not queue._assemble()  # finite target never overshoots
    with SessionLocal() as db:
        book = db.scalars(select(GeneratedMock).where(GeneratedMock.status == "pending_use",
            GeneratedMock.questions.contains(tag))).first()
        assert book and len(json.loads(book.questions)) == 5
        assert pool_core.verified_booklet(book.questions)


def test_no_automatic_import_of_old_quarantined_booklets(setup):
    settings, tag = setup
    queue.recover_interrupted()
    assert queue.snapshot()["pending_booklets"] == 0


def test_verifier_health_uses_groq_fallback_without_resetting_gemini_limits(setup):
    settings, tag = setup
    identity = provider_quota.quota_identity(settings.GEMINI_BASE_URL, settings.GEMINI_MODEL_NAME, "verifier-key")
    provider_quota._BLOCKS[identity] = ((queue._now() + timedelta(hours=1)).replace(tzinfo=queue.timezone.utc).timestamp(), "daily")
    health = provider_quota.pool_verification_status(settings)
    assert not health["blocked"] and health["provider"] == "groq" and health["fallback"]
    assert provider_quota.blocked_quota(identity)


def test_verifier_factory_switches_provider_and_groq_keys_on_limits(setup, monkeypatch):
    settings, tag = setup
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    created = []
    class Client(Solver):
        def __init__(self, provider, key):
            super().__init__(); self.provider = provider; self.key = key
        def generate(self, messages, **kwargs):
            created.append((self.provider, self.key))
            if self.provider == "gemini" or self.key == "draft-key":
                self.last_error_code = "provider_daily_quota"; return ""
            return '{"answers":[{"id":1,"answer":0}]}'
    monkeypatch.setattr(llm, "get_llm_client", lambda provider, api_key, model: Client(provider, api_key))
    client = llm.get_pool_verifier_client()
    assert client.generate([{"role": "user", "content": "blind solve"}])
    assert created == [("gemini", "verifier-key"), ("groq", "draft-key"), ("groq", "backup-key")]
