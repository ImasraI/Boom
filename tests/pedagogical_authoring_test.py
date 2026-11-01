"""Synthetic contracts only. No provider calls, private corpus or DB writes."""
import copy
import json
import pytest
from app.rag.pedagogical_authoring import parse_pedagogical_candidate,teaching_holds,render_figure,prompt_for


@pytest.fixture
def candidate():
    return {'text':'Synthetic $x+1=2$', 'options':['1','2','3','4'],'answer_index':0,
      'solution':'Subtract one on both sides, so x=1.',
      'design':{k:'Synthetic evidence' for k in ['givens','unknown','domains','essential_insight','structural_departure','tempting_wrong_route']},
      'figure':None,'pedagogy':{'key_observation':'The same subtraction preserves equality.',
        'steps':[{'id':'s1','explanation':'Subtract one from each side.','math':'x=2-1=1'}],
        'proposed_techniques':[{'id':'tech.equation_setup','role':'primary','step_ids':['s1'],
          'evidence':'Synthetic linkage; not semantic validation.','symmetry_witness':None}],
        'boundary_checks':['1+1=2 satisfies the given equation.'],'answer_justification':'Option one is exactly one.',
        'alternative_route':None},'verification_record':{'method':'symbolic','summary':'Substitution gives equality.','claimed_by':'author_model'}}


def test_typed_solution_preserved_without_approval(candidate):
    result=parse_pedagogical_candidate(json.dumps(candidate))
    assert result==candidate and teaching_holds(result)==[]
    assert 'eligible' not in result and 'human_approved' not in result


@pytest.mark.parametrize('mutation',[
 lambda q:q['pedagogy'].update(steps=[]),
 lambda q:q['pedagogy']['steps'].append(copy.deepcopy(q['pedagogy']['steps'][0])),
 lambda q:q['pedagogy']['proposed_techniques'][0].update(step_ids=['s99']),
 lambda q:q['pedagogy']['proposed_techniques'][0].update(step_ids=['s1','s1']),
 lambda q:q['pedagogy']['proposed_techniques'][0].update(id='tech.invented'),
 lambda q:q['pedagogy']['proposed_techniques'][0].update(id=[]),
 lambda q:q['pedagogy']['proposed_techniques'][0].update(role='human_approved'),
 lambda q:q['pedagogy']['proposed_techniques'][0].update(id='tech.symmetry'),
 lambda q:q['pedagogy'].update(key_observation=''),
 lambda q:q['pedagogy']['steps'][0].update(math=''),
 lambda q:q['verification_record'].update(claimed_by='human'),
 lambda q:q.update(answer_index=True),
 lambda q:q.update(eligible=True),
 lambda q:q['pedagogy'].update(boundary_checks='verified'),
 lambda q:q.update(figure={'points':{'A':[0,0],'O':[1,1]},'segments':[],'circles':[{'center':'O','through':'Z'}]}),
 lambda q:q.update(figure={'points':{'A':[0,0],'O':[1,1]},'segments':[],'circles':[{'center':'O','through':'O'}]}),
])
def test_malformed_and_false_authority_records_rejected(candidate,mutation):
    mutation(candidate)
    with pytest.raises(ValueError):parse_pedagogical_candidate(json.dumps(candidate))


def test_unknown_annotations_are_holds_not_approved(candidate):
    candidate['pedagogy'].update(proposed_techniques=[],boundary_checks=[])
    result=parse_pedagogical_candidate(json.dumps(candidate))
    assert teaching_holds(result)==['techniques_unresolved','boundary_checks_unresolved']


def test_symmetry_requires_transformation_and_preserved_property(candidate):
    tag=candidate['pedagogy']['proposed_techniques'][0];tag['id']='tech.symmetry'
    tag['symmetry_witness']={'transformation':'Swap a and b.','preserved':'Both given relations.','conclusion':'Use symmetric variables; not a=b.'}
    assert parse_pedagogical_candidate(json.dumps(candidate))==candidate


def test_circle_renderer_uses_full_extent_and_safe_elements(candidate):
    candidate['figure']={'points':{'O':[0,0],'A':[2,0],'B':[0,2]},'segments':[['A','B']],
                         'circles':[{'center':'O','through':'A'}]}
    q=parse_pedagogical_candidate(json.dumps(candidate));svg=render_figure(q['figure'])
    assert 'r="165.000000"' in svg and 'direction="ltr"' in svg
    assert 'cx="210.000000"' in svg and '<script' not in svg


def test_duplicate_json_keys_rejected(candidate):
    raw=json.dumps(candidate).replace('"answer_index": 0','"answer_index": 0,"answer_index": 1')
    with pytest.raises(ValueError):parse_pedagogical_candidate(raw)


def test_new_prompt_separates_teaching_verification_and_proposed_tags():
    p=prompt_for({'id':'synthetic','facts':['Synthetic fact']})
    assert 'verification_record' in p and 'symmetry_witness' in p
    assert 'human/scientific approval' in p and 'not just an answer' in p


def test_published_json_schema_accepts_synthetic_shape_and_rejects_false_authority(candidate):
    from jsonschema import Draft202012Validator
    from app.rag.pedagogical_schema import schema
    contract=schema();Draft202012Validator.check_schema(contract);validator=Draft202012Validator(contract)
    validator.validate(candidate)
    candidate['human_approved']=True
    assert list(validator.iter_errors(candidate))


def test_schema_requires_symmetry_witness_but_does_not_certify_its_truth(candidate):
    from jsonschema import Draft202012Validator
    from app.rag.pedagogical_schema import schema
    validator=Draft202012Validator(schema());tag=candidate['pedagogy']['proposed_techniques'][0]
    tag['id']='tech.symmetry'
    assert list(validator.iter_errors(candidate))
    tag['symmetry_witness']={'transformation':'Synthetic swap','preserved':'Synthetic relation','conclusion':'Synthetic proposal'}
    validator.validate(candidate)
