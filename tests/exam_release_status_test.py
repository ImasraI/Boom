import importlib.util
from pathlib import Path
from app.rag.exam_corpus import atomic_json


def load_script():
    path = Path(__file__).resolve().parents[1] / 'backend/scripts/exam_release_status.py'
    spec = importlib.util.spec_from_file_location('exam_release_status', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_completed_vectors_do_not_approve_unreviewed_corpus(tmp_path):
    atomic_json(tmp_path / 'manifest.json', {'chunks_sha256': 'snapshot'})
    atomic_json(tmp_path / 'embedding-status.json', {
        'phase': 'complete', 'stored_chunks': 10, 'total_chunks': 10})
    atomic_json(tmp_path / 'retrieval-pilot.json', {'snapshot_sha256': 'snapshot',
        'embedding_complete': True, 'gold_sources': 20, 'held_out_documents': 3,
        'subject_coverage': ['ریاضی', 'فیزیک', 'شیمی'],
        'selected_policy_metrics': {'queries': 30, 'recall_at_5': 1, 'mrr': 1}})
    atomic_json(tmp_path / 'generation-pilot.json', {'verified': 20})
    report = load_script().build_report(tmp_path)
    assert report['ready'] is False
    assert report['automatic_activation'] is False
    assert report['reasons'] == ['source_curriculum_science_difficulty_and_novelty_reviews_required']


def test_stale_retrieval_evaluation_is_explicitly_held(tmp_path):
    atomic_json(tmp_path / 'manifest.json', {'chunks_sha256': 'new'})
    atomic_json(tmp_path / 'retrieval-pilot.json', {'snapshot_sha256': 'old'})
    assert 'evaluation_snapshot_mismatch' in load_script().build_report(tmp_path)['reasons']
