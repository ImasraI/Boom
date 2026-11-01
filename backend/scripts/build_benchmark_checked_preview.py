"""Separate repaired presentation; frozen raw experiment outcomes never change."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import figure_svg,saved_json,execution_lock
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.check_benchmark_algebra_slice import CASES
from scripts.check_benchmark_saved_slice import REST
from scripts.check_benchmark_figures import audit_candidate,RELATIONS
from scripts.run_authoring_benchmark import ROOT,OUT,load_protocol


def corrected_candidate(item,candidate):
    expected={**CASES,**REST}[item][0]
    if payload_digest(candidate)!=expected:raise ValueError('Correction input changed')
    q=copy.deepcopy(candidate);changes=[]
    if item=='pair-06-baseline':
        if q['options'][3]!='$([0, 4)$':raise ValueError('Unexpected distractor')
        q['options'][3]='$[0, 4)$';changes.append('Editorial choice: malformed fourth interval rewritten as [0,4); k=0 is impossible, so it remains incorrect')
    elif item=='pair-07-baseline':
        if q['text'].count('\\mathbb{R}^2')!=1:raise ValueError('Unexpected math delimiter defect')
        q['text']=q['text'].replace('\\mathbb{R}^2','$\\mathbb{R}^2$')
        changes.append('Added missing math delimiters around the real-plane symbol')
    elif item=='pair-09-baseline':
        q['figure']['points']['P']=[70/13,100/13]
        changes.append('Restored computed intersection coordinates instead of three-decimal rounding')
    elif item=='pair-12-baseline':
        q['figure']['points']['N']=[0,16/3]
        changes.append('Restored AN/AM=1/3 instead of rounded point placement')
    elif item=='pair-14-baseline':
        q['figure']['points']={'A':[0,0],'B':[0,-8],'C':[16,0],'D':[0,-3],
            'F':[0,-5],'E':[6,0],'G':[10,0]}
        changes.append('Reconstructed a consistent triangle with AB=8,AC=16 and the declared parallel-section fractions')
    return q,changes


def main():
    if Path.cwd().resolve()!=ROOT/'backend':raise ValueError('Run from backend')
    load_protocol()
    pointer=saved_json(OUT/'review-pointer.json');name=pointer['folder']
    if Path(name).name!=name:raise ValueError('Invalid parent review pointer')
    parent=OUT/name;binding=saved_json(parent/'binding.json')
    if payload_digest(binding)!=pointer['binding_sha256']:raise ValueError('Parent binding changed')
    folder=OUT/'independent-saved-slice-v1';p=saved_json(folder/'status.json')
    if Path(p['artifact']).name!=p['artifact']:raise ValueError('Invalid check pointer')
    report=saved_json(folder/p['artifact'])
    if payload_digest(report)!=p['sha256']:raise ValueError('Independent check report changed')
    proofs={r['item_id']:r for r in report['records']}
    questions=[];solutions=[];deltas=[];figures=[]
    for r in binding['records']:
        item=r['item_id'];original=r['candidate'];proof=proofs[item]
        if payload_digest(original)!=r['candidate_sha256'] or proof['candidate_sha256']!=r['candidate_sha256']:
            raise ValueError('Stale math/candidate binding')
        if proof['answer_index_expected']!=original['answer_index']:raise ValueError('Answer disagreement held')
        q,changes=corrected_candidate(item,original)
        checks=['Assistant symbolic/finite replay; no expert scientific approval',
            'Model blind comparisons apply to the original snapshot; this is an explicit presentation revision']
        if item in RELATIONS:
            audit=audit_candidate(item,q)
            if not audit['audit']['all_passed']:raise ValueError('Repaired figure still violates declared constraints')
            figures.append(dict(alias=r['alias'],audit=audit));checks.append('Assistant-declared coordinate relations pass at1e-7 tolerance')
        checks.extend(changes)
        questions.append(dict(id=r['alias'],stem=q['text'],options=q['options'],svg=figure_svg(q['figure'])))
        solutions.append(dict(id=r['alias'],answer_index=proof['answer_index_expected'],answer_latex='',
            proof=proof['independent_derivation'],checks=checks))
        deltas.append(dict(alias=r['alias'],item_id=item,original_candidate_sha256=r['candidate_sha256'],
            presented_question_sha256=payload_digest(dict(text=q['text'],options=q['options'],figure=q['figure'])),changes=changes))
    completion=('۴۰ تلاشِ برنامه‌ریزی‌شده تمام شده است؛ شکست سرویس یا قالب، سؤال محسوب نمی‌شود.'
        if binding['generation_complete'] else 'تلاش‌های برنامه‌ریزی‌شده هنوز تمام نشده‌اند.')
    presentation=dict(questions=questions,solutions=solutions,review_only=True,proof_kind='independent_assistant',
        provenance=f'این {len(questions)} پیش‌نویس را مدل زبانی تولید کرده است. نسخهٔ نمایش با اصلاح شکل‌ها، نشانه‌گذاری و یک گزینهٔ بدنوشت آماده شده؛ متن خام و خطاها حفظ شده‌اند. داوری انسانی فقط دربارهٔ همین نسخه ثبت خواهد شد. '+completion)
    manifest=dict(schema_version='0.1',presentation_revision=1,parent_review_binding_sha256=pointer['binding_sha256'],
        independent_checks_sha256=p['sha256'],presentation_sha256=payload_digest(presentation),deltas=deltas,figure_audits=figures,
        human_review=False,eligible=False,original_outcomes_rewritten=False,
        scope='Repaired editorial preview; cannot be used to claim unedited model output quality')
    target=OUT/('checked-preview-'+payload_digest(manifest));target.mkdir(exist_ok=True)
    with execution_lock(target):
        for name,data in [('manifest.json',manifest),('presentation.json',presentation)]:
            path=target/name
            if path.exists() and saved_json(path)!=data:raise ValueError('Frozen checked preview changed')
            if not path.exists():atomic_json(path,data)
        pages=target/'pages';pages.mkdir(exist_ok=True);prior=saved_json(target/'status.json',None)
        if prior:
            for name,digest in prior['page_sha256'].items():
                if hashlib.sha256((pages/name).read_bytes()).hexdigest()!=digest:raise ValueError('Checked preview page changed')
        else:
            result=subprocess.run(['node',str(ROOT/'frontend/tools/render-authoring-trial.cjs'),str(pages)],
                input=json.dumps(presentation,ensure_ascii=False).encode(),capture_output=True,check=True)
            rendering=json.loads(result.stdout)
            if rendering['errors']:raise ValueError('Checked preview has rendering errors')
            atomic_json(target/'status.json',dict(rendering=rendering,manifest_sha256=payload_digest(manifest),
                page_sha256={name:hashlib.sha256((pages/name).read_bytes()).hexdigest()
                    for name in ('questions.html','solutions.html','render-validation.json')}))
        atomic_json(OUT/'checked-preview-pointer.json',dict(folder=target.name,manifest_sha256=payload_digest(manifest)))
        print(json.dumps(dict(folder=target.name,questions=len(questions),figure_audits=len(figures),
            corrected_questions=sum(bool(d['changes']) for d in deltas),eligible=0)))


if __name__=='__main__':main()
