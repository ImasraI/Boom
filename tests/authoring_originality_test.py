import pytest
from app.rag.authoring_originality import screen, originality_contract
from app.rag.question_design import authoring_contract


@pytest.mark.parametrize('other', ['اگر عدد ۴ را با ۷ جمع کنیم چه میشود؟',
                                  'اگر عدد 9 را با 12 جمع کنیم چه میشود؟'])
def test_number_changes_are_held(other):
    result = screen(other, [{'id': 'synthetic-1', 'text': 'اگر عدد 2 را با 3 جمع کنیم چه میشود؟'}])
    assert result['state'] == 'held_close_variant'
    assert result['matches'][0]['reference_id'] == 'synthetic-1'
    assert result['originality_approved'] is False


def test_no_match_does_not_certify_originality():
    assert screen('Find the area of a triangle.', [])['state'] == 'pending_semantic_review'


def test_report_does_not_repeat_source_text():
    result = screen('Secret example 12', [{'id': 'synthetic', 'text': 'Secret example 24'}])
    assert 'Secret' not in str(result)


def test_existing_authoring_prompt_includes_relationship_changes():
    assert originality_contract() in authoring_contract('konkur')
    assert 'practice variant' in originality_contract()


def test_empty_question_is_invalid():
    with pytest.raises(ValueError):
        screen('', [])
