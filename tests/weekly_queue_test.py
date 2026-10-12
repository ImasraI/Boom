"""A weekly run must not spend its queue slots or reviews on old mock drafts."""
import json

from app.auth.database import PoolDraftJob, SessionLocal
from app.rag import pool_queue as queue, weekly_ranked, exam_blueprint
from pool_queue_test import setup, config, draft, question


def scoped_config(original, scope='next-exam'):
    return {**original, 'weekly_scope': scope, 'weekly_plan': [{
        'name': 'ریاضی', 'questions': 4, 'curriculum_ids': ['lesson:allowed'],
        'weekly_ranked_scope': scope}]}


def test_old_drafts_do_not_block_or_consume_weekly_slots_and_reviews(setup, monkeypatch):
    _, tag = setup
    old = [draft(tag + str(i)) for i in range(2)]
    monkeypatch.setattr(weekly_ranked, 'prepare_config', scoped_config)
    weekly = {**config(), 'kind': 'weekly_ranked'}
    new = [queue.create_job(weekly, 'riazi', 'duel') for _ in range(3)]
    assert all(new[:2]) and new[2] is None
    for job_id in new[:2]:
        queue.append_batch(job_id, [{**question(tag + str(job_id)), 'curriculum_id': 'lesson:allowed',
                                    'weekly_ranked_scope': 'forged-old-scope'}])
        queue.finish_draft(job_id)
    assert queue.snapshot('next-exam')['pending_booklets'] == 2
    assert queue.claim_job('next-exam') == new[0]
    assert queue.claim_job('later-exam') is None
    with SessionLocal() as db:
        assert all(db.get(PoolDraftJob, job_id).status == 'pending' for job_id in old)
        assert json.loads(db.get(PoolDraftJob, new[0]).questions)[0]['weekly_ranked_scope'] == 'next-exam'


def test_out_of_scope_draft_is_not_added_to_weekly_queue(setup, monkeypatch):
    _, tag = setup
    monkeypatch.setattr(weekly_ranked, 'prepare_config', scoped_config)
    job = queue.create_job({**config(), 'kind': 'weekly_ranked'}, 'riazi', 'duel')
    queue.append_batch(job, [{**question(tag), 'curriculum_id': 'lesson:unrelated'}])
    queue.finish_draft(job)
    with SessionLocal() as db:
        assert db.get(PoolDraftJob, job).question_count == 0


def test_reviewed_partial_ocr_wins_over_larger_noisy_text_in_other_folder(tmp_path, monkeypatch):
    root = tmp_path / 'ocr'
    (root / 'book' / 'pages').mkdir(parents=True)
    (root / 'book.pdf').mkdir()
    (root / 'book' / 'pages' / 'page_0239.json').write_text(json.dumps({
        'reviewed': True, 'data': {'page_text': 'حرکت بر خط راست\nمتن بازبینی‌شدهٔ کتاب'}}), encoding='utf-8')
    (root / 'book.pdf' / 'page_0239.txt').write_text('حرکت بر خط راست ' + 'نویز ' * 1000, encoding='utf-8')
    monkeypatch.setattr(exam_blueprint, 'get_settings', lambda: type('Settings', (), {'OCR_DIR': str(root)})())
    node = {'title': 'حرکت بر خط راست', 'sources': [{'book': 'book.pdf', 'page': 239}]}
    monkeypatch.setattr(exam_blueprint, 'load_catalog', lambda: {'nodes': [node]})
    excerpt = exam_blueprint.book_excerpt(node)
    assert 'بازبینی' in excerpt['quote'] and 'نویز' not in excerpt['quote']
