import json
import pytest
from app.rag.decision_evaluation import packets,stem_prompt,option_prompt,validate_stem_result,validate_option_result


def candidate():
    return {'text':'Synthetic relation x+1=2. Find x.','options':['1','2','3','4'],
            'answer_index':0,'solution':'PRIVATE_AUTHOR_SOLUTION',
            'audit_proposals':{'secret':'PRIVATE_DISTRACTOR_NOTES'},'user_id':123456}


def test_independent_projections_withhold_answers_notes_and_option_cues():
    p=packets(candidate());stem=stem_prompt(p['stem_only']);aware=option_prompt(p['option_aware'])
    assert 'options' not in p['stem_only'] and p['option_aware']['options']==['1','2','3','4']
    for prompt in (stem,aware):
        assert 'PRIVATE_AUTHOR_SOLUTION' not in prompt and 'PRIVATE_DISTRACTOR_NOTES' not in prompt
        assert '123456' not in prompt and 'answer_index' not in prompt
    assert p['eligible'] is False


def test_option_packet_cannot_be_passed_as_stem_only():
    with pytest.raises(ValueError):stem_prompt(packets(candidate())['option_aware'])


def test_free_answer_is_retained_without_automatic_option_matching():
    p=packets(candidate())['stem_only']
    r=validate_stem_result(json.dumps({'id':p['id'],'verdict':'solved','answer_expression':'1',
        'justification':'Subtract one from both sides.'}),p)
    assert 'expected_answer' not in r and 'matched' not in r


@pytest.mark.parametrize('change',[
 {'id':'wrong'}, {'verdict':'approved'}, {'verdict':'underdetermined','answer_expression':'1'},
 {'answer_expression':None},{'justification':''},{'eligible':True}])
def test_invalid_free_responses_fail_closed(change):
    p=packets(candidate())['stem_only']
    r={'id':p['id'],'verdict':'solved','answer_expression':'1','justification':'Synthetic proof.'};r.update(change)
    with pytest.raises(ValueError):validate_stem_result(json.dumps(r),p)


def test_option_audit_is_a_proposal_not_an_approved_shortcut():
    p=packets(candidate())['option_aware']
    r={'id':p['id'],'observations':[{'method':'bounds','classification':'unresolved',
        'conditions':'Synthetic conditions.','evidence':'Needs a real mathematical check.'}],
        'final_answer':None,'justification':'No conclusion is certified.'}
    assert validate_option_result(json.dumps(r),p)==r
    assert 'eligible' not in r and 'approved' not in r
    r['observations'][0]['method']='diagram_measurement'
    with pytest.raises(ValueError):validate_option_result(json.dumps(r),p)


def test_malformed_envelope_is_preserved_without_becoming_a_draft(tmp_path):
    from scripts.run_decision_pilot import save_return
    raw='{"wrong":true}'
    r=save_return(tmp_path,raw,{'protocol_sha256':'synthetic'})
    assert r['state']=='protocol_held' and r['eligible'] is False
    assert (tmp_path/(r['response_sha256']+'.txt')).read_text()==raw
    assert not (tmp_path/'candidate.json').exists() and not (tmp_path/'audit-proposals.json').exists()
