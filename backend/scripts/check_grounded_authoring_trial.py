"""Independent bounded derivations for the frozen attempt8 drafts, not a general solver."""
import hashlib
import json
import sys
from pathlib import Path
import sympy as S
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import atomic_json,payload_digest
from app.rag.authoring_originality import screen


def main():
    base=Path(__file__).resolve().parents[1]/'data/authoring_work'
    folder=base/'grounded-authoring-trial-v1/attempt-8'
    sha='9d7de37ae7b6e70211fda799367a15283893d346f4e388fabd44fec2c6188586'
    raw=(folder/(sha+'.txt')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Frozen response changed')
    drafts=json.loads(raw)['questions']
    if len(drafts)!=3 or [q['brief_id'] for q in drafts]!=['cubic_identity','parallel_similarity','residue_cycles']:
        raise ValueError('Unexpected frozen draft ordering')
    s=S.symbols('s',real=True)
    assert S.expand((s-3)*(s*s+3*s+3))==s**3-6*s-9
    assert S.discriminant(s*s+3*s+3,s)==-3
    assert 1*2==2 and 1**3+2**3==9
    residues=[n for n in range(1,1001) if n%3==1 and n%5==2]
    assert len(residues)==67 and residues[0]==7 and residues[-1]==997
    assert residues==list(range(7,1001,15))
    examples=[]
    for c in [S.Integer(5),S.Integer(12)]:
        # B=(0,0), A=(5,0), C=(0,c), D=(2,0), E=(0,2c/5).
        de=S.Matrix([-2,2*c/5]);ac=S.Matrix([-5,c])
        assert de[0]*ac[1]-de[1]*ac[0]==0
        ratio=S.simplify(S.sqrt(de.dot(de))/c)
        examples.append(dict(c=str(c),de_over_bc=str(ratio)))
    assert S.simplify(2*S.sqrt(2)/5-S.Rational(13,30))!=0
    merged=base/'reasoning-merged-v1'
    state=json.loads((merged/'status.json').read_text())
    bundle=json.loads((merged/state['artifact']).read_text(encoding='utf8'))
    if payload_digest(bundle)!=state['sha256']:raise ValueError('Development reference changed')
    references=[]
    for r in bundle['records']:
        stem=r['literal']['stem']
        if isinstance(stem,list) and all(isinstance(p,dict) and isinstance(p.get('value'),str) for p in stem):
            stem=' '.join(p['value'] for p in stem)
        if not isinstance(stem,str):raise ValueError('Unsupported source stem representation')
        references.append({'id':r['question_ref'],'text':stem})
    verdicts=[
        dict(brief_id='cubic_identity',math_state='passed_bounded_checks',computed_answer='3',
            option_index=0,decision='held_design_quality',
            reason='Correct direct cubic-identity substitution; claimed structural departure is only introducing the usual sum variable. Too routine for the stated pilot.',
            evidence=['Cubic factors into (s−3)(s²+3s+3); quadratic discriminant −3.',
                      'Existence witness a=1,b=2 meets every condition.']),
        dict(brief_id='parallel_similarity',math_state='failed',computed_answer=None,
            option_index=None,decision='rejected_underdetermined_geometry',
            reason='BDE and BAC are similar; DE/AC=2/5. DE/BC depends on AC/BC, which was not given. ADE is not the claimed similar triangle.',
            counterexamples=examples,
            evidence=['Two nondegenerate right triangles with AB=5 and BC=5 or12 both meet the givens but give different DE/BC.']),
        dict(brief_id='residue_cycles',math_state='passed_bounded_checks',computed_answer='67',
            option_index=1,decision='held_design_quality',
            reason='Correct but elementary intersection of two residue classes followed by one arithmetic-progression count.',
            evidence=['Exhaustive independent count over all1000 integers agrees with 7+15k, k=0..66.',
                      'No advanced theorem needed: enumerate residues0..14 and find only7.'])]
    for q,v in zip(drafts,verdicts):
        v['surface_screen']=screen(q['text'],references)
        v['semantic_originality_approved']=False
        v['human_reviewed']=False
        v['eligible']=False
    report=dict(schema_version='0.1',response_sha256=sha,development_reference_sha256=state['sha256'],
        check_scope='Only these frozen three drafts; assistant mathematical analysis plus symbolic/finite reproduction',
        model_agreement_used=False,checks=verdicts,
        summary=dict(drafts=3,math_passed=2,math_failed=1,design_holds=2,ready_for_editorial_preview=0,eligible=0),
        limitations=['Tiny manually reviewed convenience sample; no general accuracy estimate',
                     'Surface screen is not semantic originality verification',
                     'No human scientific review or production eligibility'])
    name='checks-'+payload_digest(report)+'.json'
    if not (folder/name).exists():atomic_json(folder/name,report)
    atomic_json(folder/'check-status.json',dict(artifact=name,sha256=payload_digest(report),**report['summary']))
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
