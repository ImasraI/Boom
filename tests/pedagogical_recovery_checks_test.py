from app.rag.pedagogical_geometry import audit
from scripts.review_pedagogical_recovery import cyclic,reflection


def test_cyclic_witness_satisfies_all_givens_and_bisector():
    q={'answer_index':1,'options':['$25^\\circ$','$30^\\circ$','$35^\\circ$','$40^\\circ$']}
    corrected,relations,proof=cyclic(q)
    assert audit(corrected['figure'],relations)['all_passed']
    assert q.get('figure') is None  # No mutation of the input record.
    assert 'beta=30' in proof and corrected['answer_index']==1


def test_reflection_stem_omits_solution_construction_and_proves_global_minimum():
    q={'answer_index':0,'options':['$17$','$19$','$21$','$25$']}
    corrected,relations,proof=reflection(q)
    assert audit(corrected['figure'],relations)['all_passed']
    assert 'A1' not in corrected['figure']['points']
    assert corrected['figure']['points']['P']==[7,0]
    assert 'every P on the entire line' in proof and 'not sqrt(241)' in proof
