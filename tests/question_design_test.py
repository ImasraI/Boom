from app.rag.question_design import assess_difficulty, authoring_contract
from app.rag.question_quality import audit
import json


def review(**patch):
    return {'meets_requested': True, 'direct_substitution_only': False,
            'interacting_concepts': ['domain constraints', 'solution counting'],
            'essential_insight': 'The parameter changes the valid domain.',
            'reason': 'Both constraints are necessary.', **patch}


def test_extra_arithmetic_does_not_make_direct_substitution_extreme():
    assert assess_difficulty('extreme', review(direct_substitution_only=True)) is False
    assert assess_difficulty('extreme', review(essential_insight='')) is False
    assert assess_difficulty('hard', review(interacting_concepts=['identity', 'identity'])) is False
    assert assess_difficulty('extreme', review()) is True


def test_missing_or_malformed_difficulty_is_not_an_approval():
    assert assess_difficulty('extreme', None) is None
    assert assess_difficulty('extreme', review(meets_requested='true')) is None
    assert assess_difficulty('extreme', review(meets_requested=None)) is None


class Client:
    def __init__(self, result): self.result = result
    def generate(self, messages, **kwargs):
        assert 'DIFFICULTY_AUDIT_V1' in messages[0]['content']
        return json.dumps(self.result)


def test_correct_but_basic_question_is_held_for_wrong_difficulty():
    result = audit(Client({'valid': True, 'reason': 'Correct answer.',
        'difficulty_review': review(direct_substitution_only=True)}), {'_requested_difficulty': 'extreme'})
    assert result['valid'] is False
    assert result['content_valid'] is True
    assert result['reason'].startswith('difficulty_below_requested_tier')


def test_no_difficulty_reply_is_deferred_not_scientifically_rejected():
    result = audit(Client({'valid': True, 'reason': 'Correct answer.'}), {'_requested_difficulty': 'extreme'})
    assert result['valid'] is None
    assert result['reason'] == 'difficulty_audit_incomplete'


def test_level_contracts_forbid_relabelled_formula_exercises():
    assert authoring_contract('easy') != authoring_contract('extreme')
    assert 'questions' in authoring_contract('extreme')
