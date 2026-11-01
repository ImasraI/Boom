import copy
import json
import pytest
from app.rag.blind_trial import make_blind_packet,solver_prompt,parse_solver_results,compare_solver_results


def presentation():
    return {'questions':[{'id':'local:q1','stem':'Synthetic x+1=3; determine x.',
        'options':['1','2','3','4'],'svg':'PRIVATE_DIAGRAM',
        'answer_index':1,'proof':'PRIVATE_PROOF','design':'PRIVATE_DESIGN'}],
        'solutions':[{'id':'local:q1','answer_index':1,'proof':'PRIVATE_PROOF'}],
        'source_refs':['PRIVATE_SOURCE']}


def solved():
    return {'results':[{'id':'blind:001','verdict':'solved','answer_index':1,'justification':'x=3−1=2.'}]}


def test_blind_projection_excludes_answers_solutions_design_figures_and_source_ids():
    p=presentation();packet,mapping=make_blind_packet(p)
    raw=json.dumps(packet);prompt=solver_prompt(packet)
    assert mapping=={'blind:001':'local:q1'}
    assert set(packet['questions'][0])=={'id','text','options'}
    for private in ('PRIVATE_PROOF','PRIVATE_DIAGRAM','PRIVATE_DESIGN','PRIVATE_SOURCE','local:q1'):
        assert private not in raw and private not in prompt
    p['questions'][0]['options'][0]='edited'
    assert packet['questions'][0]['options'][0]=='1'


@pytest.mark.parametrize('mutation',[
    lambda d:d['results'][0].update(answer_index=True),
    lambda d:d['results'][0].update(answer_index=4),
    lambda d:d['results'][0].update(verdict='ambiguous'),
    lambda d:d['results'][0].update(human_reviewed=True),
    lambda d:d['results'][0].update(id='unknown'),
    lambda d:d['results'][0].update(justification='bad '+chr(12)+'rac'),
    lambda d:d['results'].append(copy.deepcopy(d['results'][0])),
    lambda d:d['results'].clear(),
])
def test_malformed_or_promoting_results_held(mutation):
    packet,_=make_blind_packet(presentation());data=solved();mutation(data)
    with pytest.raises(ValueError):parse_solver_results(json.dumps(data),packet)


@pytest.mark.parametrize('verdict,index,expected',[
    ('solved',1,'matched'),('solved',2,'disagreed'),('ambiguous',None,'unresolved'),
    ('cannot_solve',None,'unresolved'),('inconsistent',None,'unresolved')])
def test_agreement_disagreement_and_uncertainty_remain_separate_from_approval(verdict,index,expected):
    p=presentation();packet,mapping=make_blind_packet(p);data=solved()
    data['results'][0].update(verdict=verdict,answer_index=index)
    parsed=parse_solver_results(json.dumps(data),packet)
    row=compare_solver_results(parsed,mapping,p['solutions'])[0]
    assert row['blind_solve_state']==expected
    assert row['eligible'] is False and row['human_scientific_review'] is False
