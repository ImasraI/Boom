"""Offline release readiness; no approvals, network calls, or production writes."""
import argparse
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.rag.exam_corpus import read_json, atomic_json
from app.rag.exam_quality import release_evaluation_reasons


def build_report(root):
    manifest = read_json(root / 'manifest.json', {})
    embedding = read_json(root / 'embedding-status.json', {})
    retrieval = read_json(root / 'retrieval-pilot.json', {})
    generation = read_json(root / 'generation-pilot.json', {})
    # This tool reports evidence; it never selects a winning policy after seeing results.
    evaluation = {**retrieval,
        'verified_generation_questions': generation.get('verified', 0)}
    reasons = release_evaluation_reasons(evaluation)
    if retrieval.get('snapshot_sha256') != manifest.get('chunks_sha256'):
        reasons.append('evaluation_snapshot_mismatch')
    if embedding.get('phase') != 'complete':
        reasons.append('embedding_job_incomplete')
    # Aggregate metrics cannot approve individual question records.
    reasons.append('source_curriculum_science_difficulty_and_novelty_reviews_required')
    return {'created_at': time.time(), 'ready': False, 'automatic_activation': False,
            'snapshot_sha256': manifest.get('chunks_sha256'),
            'stored_chunks': embedding.get('stored_chunks', 0),
            'total_chunks': embedding.get('total_chunks', 0),
            'reasons': list(dict.fromkeys(reasons))}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=BACKEND / 'data/exam_staging/batch-5000-v1')
    args = parser.parse_args()
    report = build_report(args.snapshot)
    atomic_json(args.snapshot / 'release-readiness.json', report)
    print(json.dumps(report, ensure_ascii=False))
