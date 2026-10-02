"""Small executable contracts for the completed reliability features."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.rag.pipeline import _answer_confidence
from app.utils import metrics


def test_confidence_signal_distinguishes_direct_and_grounded_answers():
    assert _answer_confidence([])["level"] == "direct"
    result = _answer_confidence([
        {"score": 0.8}, {"score": 0.75},
    ])
    assert result["level"] == "high"
    assert 0 < result["score"] <= 1


def test_metrics_snapshot_contains_only_aggregated_counters():
    metrics.record_request("GET", "/api/health", 200)
    metrics.record_error("test-error")
    result = metrics.snapshot()
    assert result["requests"]["GET /api/health 2xx"] >= 1
    assert result["errors"]["test-error"] >= 1