"""Reproduce checks and create a separate versioned preview for frozen attempt10.

No provider calls, arbitrary model expression execution, pool or review writes.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sympy as S
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.grounded_authoring_trial import parse_drafts
from app.rag.authoring_originality import screen
from scripts.run_grounded_authoring_trial import current_inputs

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'backend/data/authoring_work'
FOLDER=BASE/'grounded-authoring-trial-v1/attempt-10'
RESPONSE_SHA='cda548e472876c2157a1c0489cf49b30dd39cc6aa90257c577f57e1fc662e2a8'
RESPONSE_BYTES_SHA='ad2d31d56bde3a85ff31b7189ad09d19fa855591987fe3587aaa2233321c1e56'


def mathematical_checks():
    a,y=S.symbols('a y',real=True)
    # Independent route: substitute x=y+a directly, not the model's sum identity.
    quadratic=S.expand(((y+a)**3-y**3-7*a)/a)
    assert quadratic==3*y*y+3*a*y+a*a-7
    assert S.discriminant(quadratic,y)==84-3*a*a
    assert 25<=28<36
    for n in range(1,6):
        roots=S.solve(quadratic.subs(a,n),y)
        assert len(roots)==2 and all(r.is_real is True for r in roots)
        assert all(S.simplify((r+n)**3-r**3-7*n)==0 for r in roots)
    assert 84-3*6**2<0
    # General sheared trapezoid: A=(0,0),B=(15,0),D=(d,h),C=(d+10,h).
    # Varying d and h checks that the answer does not assume reflection symmetry.
    d,h,t,u=S.symbols('d h t u',real=True)
    intersection=S.solve([t*(d+10)-(15+u*(d-15)),t*h-u*h],(t,u))
    # Solve after declaring h nonzero via the vertical equation t=u.
    tval=S.solve(t*(d+10)-(15+t*(d-15)),t)[0]
    assert tval==S.Rational(3,5)
    mx=tval*d;nx=15+tval*(d-5);ox=tval*(d+10)
    px=d+(tval-1)*(d-5)
    assert S.simplify(ox-mx)==6 and S.simplify(nx-ox)==6
    assert S.simplify(nx-px)==10 and S.simplify(px-mx)==2
    assert S.simplify(ox-px)==4
    assert intersection[t]==tval and intersection[u]==tval
    for offset in (-30,-3,0,4,20):
        for height in (1,7,30):
            coords=[S.Matrix([0,0]),S.Matrix([15,0]),S.Matrix([offset+10,height]),S.Matrix([offset,height])]
            A,B,C,D=coords
            O=A+tval*(C-A);M=A+tval*(D-A);N=B+tval*(C-B)
            P=D+(tval-1)*(C-B)
            assert O[1]==M[1]==N[1]==P[1] and O[0]-P[0]==4
            assert M[0]<P[0]<O[0]<N[0]
    # Independent enumeration with modular exponentiation, no huge powers/CRT.
    residues=[n for n in range(1,21) if (pow(3,n,5)+n*n)%5==0]
    assert residues==[6,8,12,14]
    valid=[n for n in range(1,61) if n%3 and (pow(3,n,5)+n*n)%5==0]
    assert valid==[8,14,26,28,32,34,46,52]
    assert pow(3,4,5)==1
    return [dict(answer='5',answer_index=2,checks=[
        'Direct substitution x=y+a yields discriminant84−3a²; a=1..5 have real solutions, every a≥6 fails.',
        'Positive integer domain enforced; both necessity and sufficiency checked.']),
        dict(answer='4',answer_index=1,checks=[
        'General sheared trapezoid gives MO=ON=6, MP=2, PN=10 and OP=4.',
        'Exact coordinates independently checked for15 different shear/height combinations; P lies on segmentMN.']),
        dict(answer='8',answer_index=1,checks=[
        'Independent exhaustive modular check over all60 admissible positive integers gives8.',
        'The20-step cycle has residues6,8,12,14; filtering multiples of3 must occur across the full range.'])]


def diagram():
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 430 400" role="img" aria-label="Trapezoid ABCD, diagonals meeting at O, parallel segment MN and line DP parallel BC">
<polygon points="40,50 340,50 300,330 100,330" fill="none" stroke="#343434" stroke-width="2"/>
<line x1="40" y1="50" x2="300" y2="330" stroke="#888" stroke-width="1.5"/>
<line x1="340" y1="50" x2="100" y2="330" stroke="#888" stroke-width="1.5"/>
<line x1="76" y1="218" x2="316" y2="218" stroke="#91483e" stroke-width="2"/>
<line x1="100" y1="330" x2="116" y2="218" stroke="#343434" stroke-width="2"/>
<circle cx="196" cy="218" r="3" fill="#343434"/><circle cx="116" cy="218" r="3" fill="#343434"/>
<text x="25" y="38" font-size="18">A</text><text x="350" y="38" font-size="18">B</text>
<text x="310" y="350" font-size="18">C</text><text x="85" y="350" font-size="18">D</text>
<text x="190" y="201" font-size="18">O</text><text x="56" y="221" font-size="18">M</text>
<text x="330" y="221" font-size="18">N</text><text x="109" y="243" font-size="18">P</text>
<text x="162" y="34" font-size="16">AB = 15</text><text x="162" y="369" font-size="16">CD = 10</text>
</svg>'''


def main():
    raw=(FOLDER/(RESPONSE_SHA+'.txt')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=RESPONSE_BYTES_SHA:raise ValueError('Frozen response bytes changed')
    if hashlib.sha256(raw.decode('utf8').replace('\r\n','\n').encode()).hexdigest()!=RESPONSE_SHA:
        raise ValueError('Original response text binding changed')
    state=json.loads((FOLDER/'status.json').read_text())
    packet=current_inputs(2)
    if payload_digest(packet)!=state['packet_sha256']:raise ValueError('Source evidence changed')
    original=json.loads(raw)
    prepared=copy.deepcopy(original)
    # One specific known corrupted LaTeX escape in design metadata only.
    field=prepared['questions'][1]['design']['tempting_wrong_route']
    if field.count('\x0c')!=1 or '\x0crac' not in field:raise ValueError('Expected editorial defect changed')
    prepared['questions'][1]['design']['tempting_wrong_route']=field.replace('\x0crac',r'\frac')
    parse_drafts(json.dumps(prepared))
    checks=mathematical_checks()
    proofs=[
        'Put x=y+a and divide by a>0. The remaining equation is 3y²+3ay+a²−7=0. Its discriminant is84−3a². Thus real solutions exist exactly when a²≤28. This is sufficient as well as necessary: choose either real quadratic root and put x=y+a. Since25≤28<36, the permitted positive integers are1,2,3,4,5. There are5.',
        'For a general trapezoid take A=(0,0), B=(15,0), D=(d,h), C=(d+10,h), h>0. Diagonal intersection gives AO/AC=BO/BD=3/5. Therefore MO=ON=6 by Thales in ACD and BDC, without assuming reflection symmetry. The correctly ordered parallelogram is D-C-N-P: DC∥PN and DP∥CN. Hence PN=10, MP=MN−PN=12−10=2 and OP=MO−MP=4. The raw draft called the parallelogram CDNP; that vertex order is corrected here. Its final claimed wrong-route value was unsupported; confusing AO/OC with AO/AC instead predicts MO=15>MN=12, already a contradiction.',
        'Modulo5, 3^n has period4 and n² has period5. Their sum has period20. In1..20 the successful residues are6,8,12,14. In1..60 the candidates are6,8,12,14,26,28,32,34,46,48,52,54. Remove the multiples of3:6,12,48,54. The remaining8 values are8,14,26,28,32,34,46,52. Direct modular enumeration independently agrees. Residue modulo3 does not repeat every20, so do not remove a fixed number from each20-block.'
    ]
    merged=BASE/'reasoning-merged-v1';ms=json.loads((merged/'status.json').read_text())
    bundle=json.loads((merged/ms['artifact']).read_text(encoding='utf8'))
    if payload_digest(bundle)!=ms['sha256']:raise ValueError('Development references changed')
    references=[]
    for r in bundle['records']:
        stem=r['literal']['stem']
        if isinstance(stem,list):stem=' '.join(p['value'] for p in stem)
        references.append(dict(id=r['question_ref'],text=stem))
    questions=[];solutions=[];records=[]
    for i,(q,check,proof) in enumerate(zip(prepared['questions'],checks,proofs),1):
        if q['answer_index']!=check['answer_index'] or q['options'][q['answer_index']]!='$'+check['answer']+'$':
            raise ValueError('Key/options changed')
        qid=f'grounded-revision2:{i}'
        questions.append(dict(id=qid,stem=q['text'],options=q['options'],svg=diagram() if i==2 else None))
        solutions.append(dict(id=qid,answer_index=check['answer_index'],answer_latex=check['answer'],
            proof=proof,checks=check['checks']))
        surface=screen(q['text'],references)
        if surface['matches']:raise ValueError('Close surface variant held')
        records.append(dict(id=qid,brief_id=q['brief_id'],mathematics=check,
            surface_screen=surface,human_reviewed=False,semantic_originality_approved=False,eligible=False))
    report=dict(schema_version='0.1',presentation_revision=1,raw_response_sha256=RESPONSE_SHA,
        raw_response_bytes_sha256=RESPONSE_BYTES_SHA,
        storage_note='Original runner translated LF to Windows CRLF; both frozen byte and normalized response-text hashes checked. Original bytes preserved.',
        source_packet_sha256=state['packet_sha256'],records=records,
        corrections=[dict(record=2,field='design.tempting_wrong_route',kind='Known JSON form-feed to LaTeX frac escape',
            changes_question=False),dict(record=2,field='solution',kind='Correct parallelogram order to DCNP; replace unsupported wrong-route number with a checked contradiction',changes_key=False),
            dict(record=1,field='solution',kind='Explicit sufficiency derivation added')],
        summary=dict(drafts=3,bounded_math_checks_passed=3,editorial_solution_corrections=2,
            metadata_escape_corrections=1,ready_for_human_editorial_review=3,eligible=0),
        limitations=['These are bounded checks of three drafts, not a universal verifier',
            'No expert scientific review, empirical difficulty or semantic originality approval',
            'Generic briefs were manually projected from reviewed summaries; no raw exam literals were sent'])
    report_sha=payload_digest(report)
    name='checks-'+report_sha+'.json'
    if not (FOLDER/name).exists():atomic_json(FOLDER/name,report)
    out=FOLDER/'review-v1';out.mkdir(exist_ok=True)
    payload=dict(questions=questions,solutions=solutions,
        provenance='متن اولیهٔ این سه سؤال را Gemini تولید کرده است. پاسخ‌ها جداگانه بررسی شده‌اند؛ اصلاحات راه‌حل و شکل هندسی در نسخهٔ بررسی ثبت شده‌اند. داوری انسانی و تأیید نوآوری هنوز انجام نشده است.')
    payload_sha=payload_digest(payload)
    saved=out/'presentation-status.json'
    if saved.exists():
        old=json.loads(saved.read_text())
        if old['payload_sha256']!=payload_sha:raise ValueError('Preserve existing preview; create a new revision')
    else:
        node=shutil.which('node')
        if not node:raise ValueError('Existing Node runtime unavailable')
        rendered=subprocess.run([node,str(ROOT/'frontend/tools/render-authoring-trial.cjs'),str(out)],
            input=json.dumps(payload),text=True,encoding='utf8',capture_output=True,timeout=45)
        if rendered.returncode:raise ValueError('Render failed')
        atomic_json(out/'prepared-presentation.json',payload)
        atomic_json(saved,dict(payload_sha256=payload_sha,check_artifact=name,check_sha256=report_sha,
            questions_html_sha256=hashlib.sha256((out/'questions.html').read_bytes()).hexdigest(),
            solutions_html_sha256=hashlib.sha256((out/'solutions.html').read_bytes()).hexdigest(),
            renderer=dict(json.loads(rendered.stdout)),human_reviewed=False,eligible=False))
    atomic_json(FOLDER/'check-status.json',dict(artifact=name,sha256=report_sha,**report['summary']))
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
