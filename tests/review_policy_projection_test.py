from copy import deepcopy
from app.rag.review_policy_projection import project_reviews


def fixture():
    binding=dict(questionId='synthetic:q',questionRevision=2,contentHash='c',cropImageHash='i',catalogueVersion='v',evidenceToken='t')
    receipt=dict(receiptId='r1',dimension='extraction',reviewerKind='human',reviewerIdentifier='synthetic-human',
        outcome='passed',binding=deepcopy(binding),evidenceToken='t')
    event=dict(kind='decision',reviewer='synthetic-human',timestamp='2026-10-25T10:00:00+00:00',receipt=receipt)
    return binding,event


def test_current_human_receipt_projects_only_its_dimension():
    b,e=fixture();r=project_reviews(b,[e])
    assert set(r['reviews'])=={'extraction'} and not r['eligible']
    assert r['reviews']['extraction']['revision']==2


def test_content_token_or_catalogue_change_invalidates_review():
    for field in ('contentHash','cropImageHash','catalogueVersion','questionRevision','evidenceToken'):
        b,e=fixture();b[field]='changed'
        assert not project_reviews(b,[e])['reviews']


def test_latest_failed_decision_blocks_older_pass_regardless_of_input_order():
    b,e=fixture();later=deepcopy(e);later['timestamp']='2026-10-25T11:00:00+00:00'
    later['receipt'].update(receiptId='r2',outcome='failed')
    assert not project_reviews(b,[later,e])['reviews']


def test_reviewer_conflict_and_model_attribution_never_approve():
    b,e=fixture();other=deepcopy(e);other['reviewer']='other';other['receipt'].update(reviewerIdentifier='other',outcome='unresolved')
    assert not project_reviews(b,[e,other])['reviews']
    e['receipt']['reviewerKind']='model'
    assert not project_reviews(b,[e])['reviews']


def test_ambiguous_order_and_malformed_events_hold_projection():
    b,e=fixture()
    assert not project_reviews(b,[e,e])['reviews']
    assert not project_reviews(b,[None,e])['reviews']
