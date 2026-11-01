import pytest
from app.rag.figure_constraints import audit_relations


def figure():
    return dict(points={'A':[0,6],'B':[0,0],'C':[6,0],'D':[2,0],
        'N':[6/7,24/7],'P':[1.2,4.8]},segments=[['A','B'],['B','C'],['C','A']])


def test_membership_parallel_and_length_ratios():
    f=figure()
    relations=[dict(kind='on_segment',points=['B','D','C']),
        dict(kind='length_ratio',segments=[['B','D'],['D','C']],value=[1,2]),
        dict(kind='on_segment',points=['A','N','D']),
        dict(kind='length_ratio',segments=[['A','N'],['N','D']],value=[3,4]),
        dict(kind='collinear',points=['B','N','P']),
        dict(kind='on_segment',points=['A','P','C']),
        dict(kind='length_ratio',segments=[['A','P'],['P','C']],value=[1,4]),
        dict(kind='parallel',segments=[['B','N'],['B','P']])]
    result=audit_relations(f,relations)
    assert result['all_passed'] and result['eligible'] is False
    # Incidence and ratios survive translation, reflection and uniform scaling.
    f['points']={k:[-7*x+50,7*y-200] for k,(x,y) in f['points'].items()}
    assert audit_relations(f,relations)['all_passed']


def test_wrong_ratio_and_point_outside_segment_are_failures():
    f=figure()
    assert not audit_relations(f,[dict(kind='length_ratio',segments=[['A','P'],['P','C']],value=[1,3])])['all_passed']
    assert not audit_relations(f,[dict(kind='on_segment',points=['N','B','P'])])['all_passed']
    assert not audit_relations(f,[dict(kind='parallel',segments=[['A','B'],['B','C']])])['all_passed']


@pytest.mark.parametrize('claim',[
    {'kind':'eval','expression':'not executable'},
    {'kind':'collinear','points':['A','A','B']},
    {'kind':'parallel','segments':[['A','B'],['C','UNKNOWN']]},
    {'kind':'length_ratio','segments':[['A','B'],['B','C']],'value':[1,0]},
    {'kind':'length_ratio','segments':[['A','B'],['B','C']],'value':[True,2]},
    {'kind':'collinear','points':['A','B','C'],'approved':True},
])
def test_unknown_or_malformed_claims_are_rejected(claim):
    with pytest.raises(ValueError):audit_relations(figure(),[claim])


def test_tiny_finite_coordinates_do_not_underflow_or_render_infinity():
    from app.rag.authoring_benchmark import figure_svg
    f=dict(points={'A':[0,0],'B':[1e-300,0],'C':[2e-300,0]},segments=[['A','C']])
    assert audit_relations(f,[dict(kind='on_segment',points=['A','B','C'])])['all_passed']
    svg=figure_svg(f)
    assert 'inf' not in svg.lower() and 'nan' not in svg.lower()


def test_bound_relation_audit_cannot_follow_changed_content():
    from app.rag.figure_constraints import audit_bound_relations
    from app.rag.exam_corpus import payload_digest
    q=dict(text='Synthetic',figure=figure())
    claims=dict(schema_version='0.1',candidate_sha256=payload_digest(q),figure_sha256=payload_digest(q['figure']),
        relations=[dict(kind='on_segment',points=['A','N','D'])])
    result=audit_bound_relations(q,claims)
    assert result['audit']['all_passed'] and result['human_scientific_review'] is False
    q['text']='Changed'
    with pytest.raises(ValueError,match='Stale'):audit_bound_relations(q,claims)
