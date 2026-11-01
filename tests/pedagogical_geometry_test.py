import copy
import pytest
from app.rag.pedagogical_geometry import audit,bound_audit
from app.rag.exam_corpus import payload_digest


def figure():return {'points':{'O':[0,0],'A':[2,0],'B':[0,2],'C':[-2,0],'D':[0,-2],'E':[1,0]},
                     'segments':[['A','C'],['B','D']],'circles':[{'center':'O','through':'A'}]}


def claims():return [
 {'kind':'on_circle','circle':0,'points':['A','B','C','D']},
 {'kind':'perpendicular','segments':[['A','C'],['B','D']]},
 {'kind':'reflection','source':'A','image':'C','axis':['O','B']},
 {'kind':'angle_degrees','points':['A','O','B'],'value':90},
 {'kind':'triangle_area','points':['A','B','C'],'value':[4,1]},
 {'kind':'convex_polygon','points':['A','B','C','D']}]


def test_independent_circle_reflection_area_angle_and_convexity_checks():
    result=audit(figure(),claims());assert result['all_passed']
    assert result['eligible'] is False and result['human_scientific_review'] is False


@pytest.mark.parametrize('bad',[
 {'kind':'on_circle','circle':0,'points':['E']},
 {'kind':'perpendicular','segments':[['A','B'],['O','B']]},
 {'kind':'reflection','source':'A','image':'D','axis':['O','B']},
 {'kind':'angle_degrees','points':['A','O','B'],'value':60},
 {'kind':'triangle_area','points':['A','B','C'],'value':[8,1]},
 {'kind':'convex_polygon','points':['A','C','B','D']},
])
def test_false_geometry_is_not_hidden(bad):assert not audit(figure(),[bad])['all_passed']


@pytest.mark.parametrize('bad',[
 {'kind':'on_circle','circle':True,'points':['A']},
 {'kind':'on_circle','circle':9,'points':['A']},
 {'kind':'on_circle','circle':0,'points':['Missing']},
 {'kind':'angle_degrees','points':['A','O','B'],'value':float('nan')},
 {'kind':'angle_degrees','points':['A','O','B'],'value':True},
 {'kind':'reflection','source':'A','image':'C','axis':['O','O']},
 {'kind':'triangle_area','points':['A','B','C'],'value':[True,1]},
 {'kind':'execute','expression':'__import__("os")'},
])
def test_invalid_typed_claims_fail_closed(bad):
    with pytest.raises(ValueError):audit(figure(),[bad])


def test_stale_figure_and_candidate_bindings_rejected():
    candidate={'figure':figure(),'text':'Synthetic'}
    record={'schema_version':'0.2','candidate_sha256':payload_digest(candidate),
            'figure_sha256':payload_digest(candidate['figure']),'relations':claims()}
    assert bound_audit(candidate,record)['audit']['all_passed']
    changed=copy.deepcopy(candidate);changed['text']='Different synthetic'
    with pytest.raises(ValueError):bound_audit(changed,record)


def test_radial_and_reflection_checks_are_scale_independent():
    f=figure();rel=[c for c in claims() if c['kind']!='triangle_area']
    for factor in (1e-4,1000):
        copy_f=copy.deepcopy(f);copy_f['points']={k:[x*factor,y*factor] for k,(x,y) in f['points'].items()}
        assert audit(copy_f,rel)['all_passed']


def test_tangent_requires_correct_circle_point_direction_and_incidence():
    f=figure();f['points'].update(T=[2,3],U=[2,1],V=[-2,3],W=[-2,1])
    good={'kind':'tangent','circle':0,'point':'A','line':['T','U']}
    assert audit(f,[good])['all_passed']
    # A parallel tangent on the OTHER side of the circle is not tangent at A.
    assert not audit(f,[{**good,'line':['V','W']}])['all_passed']
    assert not audit(f,[{**good,'line':['A','B']}])['all_passed']
    assert not audit(f,[{**good,'point':'E'}])['all_passed']


def test_explicit_circle_position_does_not_treat_boundary_as_inside():
    f=figure();f['points']['P']=[3,0]
    for point,position in [('O','inside'),('A','on'),('P','outside')]:
        assert audit(f,[{'kind':'point_circle_position','circle':0,'point':point,'position':position}])['all_passed']
    assert not audit(f,[{'kind':'point_circle_position','circle':0,'point':'A','position':'inside'}])['all_passed']


def test_rotation_translation_and_reversing_convex_order_preserve_geometry():
    import math
    f=figure();f['points']={k:[(x-y)/math.sqrt(2)+100,(x+y)/math.sqrt(2)-50] for k,(x,y) in f['points'].items()}
    assert audit(f,claims())['all_passed']
    assert audit(f,[{'kind':'convex_polygon','points':['D','C','B','A']}])['all_passed']


def test_self_crossing_star_is_not_accepted_as_convex():
    import math
    f={'points':{chr(65+i):[math.cos(2*math.pi*i/5),math.sin(2*math.pi*i/5)] for i in range(5)},'segments':[],'circles':[]}
    assert audit(f,[{'kind':'convex_polygon','points':['A','B','C','D','E']}])['all_passed']
    assert not audit(f,[{'kind':'convex_polygon','points':['A','C','E','B','D']}])['all_passed']
