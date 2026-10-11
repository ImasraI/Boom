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
