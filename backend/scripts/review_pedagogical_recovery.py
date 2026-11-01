"""Check, blind-solve or render the separately frozen provider-recovery drafts."""
import argparse
import copy
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_pedagogical_recovery import OUT,ROOT


def cyclic(q):
    assert q['answer_index']==1 and q['options']==['$25^\\circ$','$30^\\circ$','$35^\\circ$','$40^\\circ$']
    cot=lambda d:1/math.tan(math.radians(d))
    u=(cot(50)+cot(80))/2;v=(cot(50)-cot(80))/2
    a=(-u,0);b=(u,0);c=(v,1);d=(-v,1)
    y0=(1+v*v-u*u)/2
    p=(0,u/(u+v))
    # BQ has direction115 degrees; intersect it with A+t(C-A).
    slope=math.tan(math.radians(115));t=(-2*u*slope)/(1-(u+v)*slope)
    pointq=(-u+t*(u+v),t)
    assert 0<p[1]<pointq[1]<1
    repaired=copy.deepcopy(q)
    repaired['figure']={'points':{k:list(v) for k,v in {'A':a,'B':b,'C':c,'D':d,'O':(0,y0),'P':p,'Q':pointq}.items()},
        'segments':[['A','B'],['B','C'],['C','D'],['D','A'],['A','C'],['B','D'],['B','Q']],
        'circles':[{'center':'O','through':'A'}]}
    relations=[{'kind':'on_circle','circle':0,'points':['A','B','C','D']},
        {'kind':'convex_polygon','points':['A','B','C','D']},
        {'kind':'parallel','segments':[['A','B'],['C','D']]},
        {'kind':'on_segment','points':['A','P','C']},{'kind':'on_segment','points':['B','P','D']},
        {'kind':'on_segment','points':['A','Q','C']},
        {'kind':'angle_degrees','points':['A','P','B'],'value':80},
        {'kind':'angle_degrees','points':['B','Q','C'],'value':115},
        {'kind':'angle_degrees','points':['D','B','Q'],'value':15},
        {'kind':'angle_degrees','points':['Q','B','C'],'value':15},
        {'kind':'angle_degrees','points':['C','A','D'],'value':30}]
    return repaired,relations,('A cyclic trapezoid is isosceles. Put alpha=angle BAC=angle ABD. '
        'Triangle PAB gives 180-2alpha=80, so alpha=50. Put beta=angle CAD=angle CBD '
        '(same chord CD). Since BPC=100, angle PCB=80-beta. In triangle PBC, '
        'the internal bisector of PBC meets PC at Q, so Q lies between P and C. '
        'Thus QCB=PCB and CBQ=beta/2. '
        'In triangle BQC, 115+(80-beta)+beta/2=180 gives beta=30. '
        'The repaired coordinate witness has convex, cyclic ABCD with both given angles and '
        'the bisector checked directly, establishing existence and the needed point order. '
        'Only option2 is30. The author alternative arc discussion is incomplete and is not needed.')


def reflection(q):
    assert q['answer_index']==0 and q['options']==['$17$','$19$','$21$','$25$']
    assert 15**2+(2+6)**2==17**2
    assert math.isclose(math.hypot(15/4,2)+math.hypot(45/4,6),17)
    repaired=copy.deepcopy(q)
    # Stem illustration keeps P generic and omits the answer-revealing reflected point.
    repaired['figure']={'points':{'A':[0,2],'B':[15,6],'C':[0,0],'D':[15,0],
        'P':[7,0],'E':[-3,0],'F':[18,0]},
        'segments':[['E','F'],['A','C'],['B','D'],['A','P'],['P','B']], 'circles':[]}
    relations=[{'kind':'collinear','points':['E','C','P']},
        {'kind':'collinear','points':['E','P','D']},{'kind':'collinear','points':['E','D','F']},
        {'kind':'perpendicular','segments':[['A','C'],['E','F']]},
        {'kind':'perpendicular','segments':[['B','D'],['E','F']]},
        {'kind':'length_ratio','segments':[['A','C'],['B','D']],'value':[1,3]},
        {'kind':'length_ratio','segments':[['C','D'],['A','C']],'value':[15,2]}]
    return repaired,relations,('Choose L as y=0, A=(0,2), B=(15,6), losing no generality by a rigid motion '
       'and possibly reflecting horizontally. Reflect A to A1=(0,-2). For every P on the entire line, '
       'AP+PB=A1P+PB>=A1B=sqrt(225+64)=17. Segment A1B crosses L at P=(15/4,0), '
       'where equality holds. This proves a global attainable minimum, not just a stationary point '
       'over the projection interval. Only option1 is17. The model counterfactual boundary sentence '
       'is wrong: if distances2 and6 are on opposite sides, direct AB is sqrt(15^2+8^2)=17, '
       'not sqrt(241). That unrelated sentence must not be taught as a valid check. '
       'The raw figure shows the solving construction and optimal P; the stem version removes A1 '
       'and places P generically. Original author text/figure remain available for inspection.')


def check():
    from scripts import check_pedagogical_pilot as checker
    checker.OUT=OUT
    checker.CHECKED={'cyclic_constraints':'4d58bd1a60bbcc5955809122b95e813344472731223cddbd5a5f02ee3c3edaaa',
        'reflection_isometry':'be5bd05467121f62c7ae7fe10e8b6b4c8e9b5b89cacb342f93e75668fedd8f19'}
    checker.CHECKERS={'cyclic_constraints':cyclic,'reflection_isometry':reflection}
    checker.REVIEW_NOTES={
        'cyclic_constraints':{'remaining_limitations':['Structured pedagogy is English.',
           'The alternative arc route is incomplete. Coordinates required correction.'],
           'structural_originality':'unresolved; parallel sides still support the cyclic mechanism'},
        'reflection_isometry':{'remaining_limitations':[
           'اشتباه در بررسی مرزی مدل: اگر دو نقطه در دو طرف خط باشند، فاصلهٔ عمودی ۸ است و پاسخ ۱۷ می‌شود؛ نه رادیکال ۲۴۱.',
           'شکل خام نقطهٔ بازتاب و جای بهینهٔ P را نشان می‌دهد؛ شکل صورت سؤال جداگانه اصلاح شده است.',
           'Structured pedagogy is English. The equation_setup tag on a Pythagorean substitution is questionable.'],
           'technique_proposals_semantically_plausible':False,
           'author_explanation_state':'held_for_counterfactual_correction'}}
    checker.main()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['check','solve','review','coverage'])
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    if args.action=='check':check()
    elif args.action=='solve':
        from scripts import solve_pedagogical_pilot as solver
        solver.OUT=OUT;solver.solve(2)
    elif args.action=='review':
        from scripts import build_pedagogical_review as builder
        builder.OUT=OUT;builder.main()
    else:
        from scripts import report_pedagogical_coverage as reporter
        reporter.OUT=OUT;reporter.main()
