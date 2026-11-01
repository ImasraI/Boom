import copy
import pytest
from app.rag.exam_corpus import payload_digest
from app.rag.local_trial_snapshot import validation_snapshot


def inputs():
    p={'questions':[{'id':'synthetic:q','stem':'Synthetic','options':['$1$','$2$','$3$','$4$'],'svg':None}],
       'solutions':[{'id':'synthetic:q','answer_index':1,'proof':'Synthetic proof'}]}
    m={'presentation_sha256':payload_digest(p),'records':[{'id':'synthetic:q','mathematics':{'answer_index':1,'answer':'2'}}]}
    b={'matrix':[{'question_id':'synthetic:q','expected_answer_index':1,'blind_solve_state':'matched',
                 'solver_verdict':'solved','solver_answer_index':1}]}
    f={'presentation_payload_sha256':payload_digest(p),'question_ids':['synthetic:q']}
    return p,m,b,f


def test_local_readiness_never_implies_release_even_with_imported_promotion_flags():
    p,m,b,f=inputs();m['eligible']=True;b['human_reviewed']=True;f['scientific_review']=True
    r=validation_snapshot(p,m,b,f)
    assert r['summary']['local_regression_ready']==1 and r['summary']['release_eligible']==0
    assert r['records'][0]['human_scientific_review'] is False
    assert r['records'][0]['semantic_originality_approved'] is False


@pytest.mark.parametrize('mutation',[
    lambda p,m,b,f:p['questions'][0].update(stem='Changed'),
    lambda p,m,b,f:m['records'][0]['mathematics'].update(answer_index=2),
    lambda p,m,b,f:b['matrix'][0].update(expected_answer_index=0),
    lambda p,m,b,f:b['matrix'].clear(),
    lambda p,m,b,f:b['matrix'].append(copy.deepcopy(b['matrix'][0])),
    lambda p,m,b,f:f.update(question_ids=[]),
])
def test_stale_or_missing_evidence_held(mutation):
    p,m,b,f=inputs();mutation(p,m,b,f)
    with pytest.raises(ValueError):validation_snapshot(p,m,b,f)


def test_blind_disagreement_prevents_local_readiness():
    p,m,b,f=inputs();b['matrix'][0].update(blind_solve_state='disagreed',solver_answer_index=2)
    r=validation_snapshot(p,m,b,f)
    assert r['summary']['local_regression_ready']==0 and r['summary']['release_eligible']==0


def test_new_editorial_feedback_does_not_reuse_stale_math_checks():
    p,m,b,f=inputs();p['questions'][0]['stem']='Different mathematics'
    f['presentation_payload_sha256']=payload_digest(p)
    with pytest.raises(ValueError):validation_snapshot(p,m,b,f)


def test_false_blind_match_flag_cannot_override_solver_disagreement():
    p,m,b,f=inputs();b['matrix'][0]['solver_answer_index']=2
    with pytest.raises(ValueError):validation_snapshot(p,m,b,f)
