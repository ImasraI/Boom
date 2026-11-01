import copy
import json
import pytest
from app.rag.decision_authoring import parse_envelope,readability,prompt_for


@pytest.fixture
def envelope():
    q={'text':'Synthetic $x=1$','options':['1','2','3','4'],'answer_index':0,
       'solution':'Synthetic complete explanation.',
       'design':{k:'Synthetic design' for k in ('givens','unknown','domains','essential_insight','structural_departure','tempting_wrong_route')},
       'figure':None,'pedagogy':{'key_observation':'Synthetic observation.',
          'steps':[{'id':'s1','explanation':'Synthetic step.','math':'x=1'}],
          'proposed_techniques':[],'boundary_checks':[],'answer_justification':'Synthetic argument.','alternative_route':None},
       'verification_record':{'method':'analytic','summary':'Synthetic unchecked claim.','claimed_by':'author_model'}}
    p={'distractors':[{'option_index':i,'error_hypothesis':'Synthetic error hypothesis.',
        'first_invalid_step':'Synthetic invalid step.','derivation_steps':['Unverified synthetic derivation.'],
        'derived_option':q['options'][i],'why_invalid':'Synthetic reason.'} for i in (1,2,3)],
       'shortcut_audit':[{'method':m,'outcome':'unresolved','conditions':'Synthetic conditions.',
          'argument':'Synthetic unresolved argument.','counterexample':None,'step_ids':['s1']} for m in ('bounds','special_case','option_testing')],
       'fast_route':None,'figure_checks':{'mode':'none','small_segment_risk':None,'label_plan':None,
          'preserved_relations':[],'relaxed_metric_relations':[]}}
    return {'candidate':q,'audit_proposals':p}


def test_shape_does_not_promote_proposed_wrong_routes_or_shortcuts(envelope):
    e=parse_envelope(json.dumps(envelope))
    assert e==envelope and 'eligible' not in e and 'observed_selection_count' not in e['audit_proposals']['distractors'][0]
    assert all(a['outcome']=='unresolved' for a in e['audit_proposals']['shortcut_audit'])


@pytest.mark.parametrize('mutation',[
 lambda e:e.update(eligible=True),
 lambda e:e['audit_proposals']['distractors'][0].update(option_index=True),
 lambda e:e['audit_proposals']['distractors'][0].update(option_index=0),
 lambda e:e['audit_proposals']['distractors'][0].update(option_index=2),
 lambda e:e['audit_proposals']['distractors'][0].update(derived_option='another result'),
 lambda e:e['audit_proposals']['distractors'][0].update(validation_state='expert_reviewed'),
 lambda e:e['audit_proposals']['distractors'][0].update(derivation_steps=[]),
 lambda e:e['audit_proposals']['shortcut_audit'][0].update(step_ids=['s99']),
 lambda e:e['audit_proposals']['shortcut_audit'][0].update(outcome='approved'),
 lambda e:e['audit_proposals']['shortcut_audit'][0].update(method='made_up'),
 lambda e:e['audit_proposals']['shortcut_audit'][0].update(method='special_case'),
 lambda e:e['audit_proposals']['shortcut_audit'].pop(),
 lambda e:e['audit_proposals'].update(fast_route={'conditions':'Synthetic claim only.'}),
 lambda e:e['audit_proposals']['figure_checks'].update(mode='exact'),
])
def test_malformed_or_promoted_claims_are_held(envelope,mutation):
    mutation(envelope)
    with pytest.raises((ValueError,TypeError)):parse_envelope(json.dumps(envelope))


def test_readability_flags_short_segments_without_moving_geometry():
    f={'points':{'P':[0,0],'A':[10,0],'B':[11,0],'O':[10,9]},
       'segments':[['P','A'],['A','B']],'circles':[{'center':'O','through':'A'}]}
    before=copy.deepcopy(f);result=readability(f,320)
    assert {'kind':'short_segment','segment':['A','B']} in result['flags']
    assert result['visual_review'] is None and result['eligible'] is False and f==before


def test_schematic_cannot_claim_exact_metric_fidelity(envelope):
    envelope['candidate']['figure']={'points':{'A':[0,0],'B':[2,0]},'segments':[['A','B']],'circles':[]}
    f=envelope['audit_proposals']['figure_checks'];f.update(mode='exact',label_plan='Synthetic plan.',
        preserved_relations=['Synthetic incidence.'],relaxed_metric_relations=['Synthetic metric exception.'])
    with pytest.raises(ValueError):parse_envelope(json.dumps(envelope))
    f['mode']='schematic'
    assert parse_envelope(json.dumps(envelope))['audit_proposals']['figure_checks']['mode']=='schematic'


def test_duplicate_keys_and_oversized_outputs_are_rejected(envelope):
    with pytest.raises(ValueError):parse_envelope('{"candidate":{},"candidate":{},"audit_proposals":{}}')
    with pytest.raises(ValueError):parse_envelope('x'*192001)


def test_prompt_preserves_shortcuts_and_does_not_claim_student_error_rates():
    p=prompt_for({'id':'synthetic','facts':[]})
    assert 'Do not hide a valid efficient solution' in p
    assert 'never claims about student data' in p
    assert 'candidate,audit_proposals' in p
