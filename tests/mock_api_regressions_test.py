"""Offline API regressions: routing, validation, and failed-generation refunds."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.routers import mocks


def test_history_route_is_not_consumed_by_mock_id():
    app = FastAPI()
    app.include_router(mocks.router)
    app.dependency_overrides[mocks.get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[mocks.get_db] = lambda: SimpleNamespace(
        execute=lambda *a: SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])))
    response = TestClient(app).get("/api/mocks/history")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("answer", ["invalid", [], {}, True, 1.5, -1, 4])
def test_invalid_answer_is_rejected_before_scoring(answer):
    with pytest.raises(ValidationError):
        mocks.SubmitPayload(answers={"1": answer})


def test_blank_and_legacy_numeric_answers_remain_supported():
    p = mocks.SubmitPayload(answers={"1": "2", "2": "", "3": None, "4": "null"})
    assert p.answers == {"1": 2, "2": None, "3": None, "4": None}


@pytest.mark.parametrize("field", ["questions_per_subject", "duration_minutes"])
def test_negative_mock_configuration_is_rejected(field):
    with pytest.raises(ValidationError):
        mocks.MockConfig(**{field: -1})


def test_generation_exception_refunds_reserved_quota(monkeypatch):
    calls = []
    monkeypatch.setattr(mocks, "consume_ai_use", lambda *a: calls.append("reserve"))
    monkeypatch.setattr(mocks, "release_ai_use", lambda *a: calls.append("refund"))
    monkeypatch.setattr(mocks.question_bank, "assemble", lambda *a, **kw: [])
    def fail(*a, **kw):
        raise RuntimeError("provider offline")
    monkeypatch.setattr(mocks.mock_generation, "generate_booklet", fail)
    with pytest.raises(RuntimeError):
        mocks.generate_mock(mocks.MockConfig(questions_per_subject=1),
                            current_user=SimpleNamespace(id=1), db=SimpleNamespace(
                                execute=lambda *a: SimpleNamespace(scalar_one_or_none=lambda: None)))
    assert calls == ["reserve", "refund"]
