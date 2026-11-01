"""Freeze a checked v2 review snapshot. Full author solutions remain visible."""
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest,atomic_json
from app.rag.authoring_benchmark import saved_json
from app.rag.pedagogical_authoring import render_figure,parse_pedagogical_candidate
from app.rag.pedagogical_repairs import load_candidate
from scripts.prepare_pedagogical_pilot import OUT,ROOT


def main():
    pointer=saved_json(OUT/'pointer.json');protocol=saved_json(OUT/pointer['file'])
    if payload_digest(protocol)!=pointer['sha256']:raise ValueError('Pilot protocol changed')
    ip=saved_json(OUT/'independent-checks/pointer.json')
    if not re.fullmatch('[a-f0-9]{64}\\.json',ip['file']):raise ValueError('Unsafe proof reference')
    checked=saved_json(OUT/'independent-checks'/ip['file'])
    if payload_digest(checked)!=ip['sha256']:raise ValueError('Proof report changed')
    proofs={r['spec_id']:r for r in checked['records']};questions=[];solutions=[];records=[];outcomes=[]
    for i,draft in enumerate(protocol['drafts'],1):
        identifier=draft['spec']['id'];folder=OUT/'items'/identifier;state=saved_json(folder/'state.json',{})
        outcomes.append({'id':identifier,'state':state.get('state','not_attempted')})
        if identifier not in proofs:continue
        q,repair_sha=load_candidate(folder,state);check=proofs[identifier]
        if repair_sha!=check.get('format_repair_sha256'):raise ValueError('Changed format repair binding')
        if payload_digest(q)!=check['candidate_sha256']:raise ValueError('Stale mathematical check')
        raw=(folder/(state['response_sha256']+'.txt')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=state['response_sha256']:raise ValueError('Saved author output changed')
        presented=check['corrected_candidate'];alias=f'P{i:02d}'
        if presented['figure'] is not None and not check['corrected_geometry_audit']['audit']['all_passed']:raise ValueError('Invalid corrected diagram')
        questions.append({'id':alias,'stem':presented['text'],'options':presented['options'],'svg':render_figure(presented['figure'])})
        solutions.append({'id':alias,'answer_index':check['answer_index_expected'],'answer_latex':'',
                          'proof':check['independent_proof'],
                          'checks':['Assistant analytical check, not expert review',check['correction_scope']]})
        record={'alias':alias,'spec_id':identifier,'candidate_sha256':payload_digest(q),'author_candidate':q,
                'independent_check':check,'format_repair_sha256':repair_sha,'blind_comparison':None}
        vf=OUT/'blind-verification-v1'/identifier
        vs=saved_json(vf/'state.json',{})
        if vs.get('state')=='compared':
            comparison=saved_json(vf/'comparison.json')
            if payload_digest(comparison)!=vs['comparison_sha256'] or comparison['candidate_sha256']!=payload_digest(q):
                raise ValueError('Stale blind comparison')
            record['blind_comparison']=comparison
        records.append(record)
    if not records:raise ValueError('No independently checked drafts available')
    provenance=('نسخهٔ آزمایشی جدید با راه‌حل آموزشی و برچسب‌های پیشنهادی. '
       'این فقط برگهٔ سؤال‌های دارای بررسی مستقلِ دستیار است؛ تلاش‌های ناموفق یا بررسی‌نشده در جدول وضعیت باقی مانده‌اند. '
       'شکل اصلاح‌شده از خروجی خام مدل جداست. تأیید علمی متخصص یا مجوز انتشار صادر نشده است.')
    presentation={'questions':questions,'solutions':solutions,'review_only':True,'proof_kind':'independent_assistant','provenance':provenance}
    manifest={'schema_version':'0.1','authoring_protocol_sha256':pointer['sha256'],'proofs_sha256':ip['sha256'],
              'presentation':presentation,'records':records,'outcomes':outcomes,'eligible':False,'human_approved':False,
              'renderer_sha256':hashlib.sha256((ROOT/'frontend/tools/render-authoring-trial.cjs').read_bytes()).hexdigest(),
              'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    digest=payload_digest(manifest);target=OUT/('review-'+digest);target.mkdir(exist_ok=True)
    path=target/'manifest.json'
    if path.exists():
        if saved_json(path)!=manifest:raise ValueError('Frozen review changed')
        if (target/'receipt.json').exists():
            receipt=saved_json(target/'receipt.json');output=target/'questions-and-solutions.html'
            if hashlib.sha256(output.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('Frozen page changed')
            print(str(output));return
    else:atomic_json(path,manifest)
    atomic_json(target/'presentation.json',presentation)
    (target/'pages').mkdir(exist_ok=True)
    result=subprocess.run(['node',str(ROOT/'frontend/tools/render-authoring-trial.cjs'),str(target/'pages')],
                          input=json.dumps(presentation,ensure_ascii=False),text=True,capture_output=True,encoding='utf8')
    if result.returncode:raise ValueError('Review rendering failed')
    rendered=saved_json(target/'pages/render-validation.json')
    if rendered.get('errors')!=0 or rendered.get('questions')!=len(records):raise ValueError('Unresolved rendering errors')
    qhtml=(target/'pages/questions.html').read_text(encoding='utf8');ahtml=(target/'pages/solutions.html').read_text(encoding='utf8')
    qa=re.findall(r'<article[^>]*>([\s\S]*?)</article>',qhtml);aa=re.findall(r'<article[^>]*>([\s\S]*?)</article>',ahtml)
    if len(qa)!=len(records) or len(aa)!=len(records):raise ValueError('Rendered alias count differs')
    escape=lambda value:html.escape(str(value),quote=True)
    sections=[]
    for record,question,answer in zip(records,qa,aa):
        q=record['author_candidate'];p=q['pedagogy'];check=record['independent_check']
        steps=''.join('<li><b dir="ltr">'+escape(s['id'])+'</b> '+escape(s['explanation'])+'<pre dir="auto">'+escape(s['math'])+'</pre></li>' for s in p['steps'])
        tags=''.join('<li><code dir="ltr">'+escape(t['id'])+'</code> · '+escape(t['role'])+' · '+escape(', '.join(t['step_ids']))+'<p>'+escape(t['evidence'])+'</p></li>' for t in p['proposed_techniques'])
        raw_diagram=('<details><summary>شکل خام Gemini — با شکل اصلاح‌شده مقایسه کن</summary>'+render_figure(q['figure'])+'</details>') if q['figure'] is not None else ''
        flag=('شکل ارائه نشده؛ سؤال از داده‌های متن قابل بررسی است' if q['figure'] is None else
              'قبول' if check['raw_geometry_audit']['audit']['all_passed'] else 'نامنطبق با قیود؛ در نسخهٔ نمایش اصلاح شده')
        limitations=check['pedagogy_review'].get('remaining_limitations',[])
        blind=record['blind_comparison']
        matches=(blind is not None and all(r['blind_solve_state']=='matched' for r in blind['matrix']))
        comparison_text=('پاسخ حل‌کنندهٔ جداگانه با کلید یکسان است؛ این تطبیق، تأیید علمی متخصص نیست.' if matches else
                         'تطبیق پاسخ هنوز تأیید نشده؛ جزئیات بررسی را ببینید.')
        sections.append('<article id="'+record['alias']+'">'+question+
          '<p><b>وضعیت شکل خام: </b>'+flag+'</p>'+raw_diagram+
          '<h3>ایدهٔ کلیدی پیشنهادی</h3><p>'+escape(p['key_observation'])+'</p><ol>'+steps+'</ol>'+
          '<h3>برچسب‌های پیشنهادی مدل — هنوز تأیید انسانی نشده</h3><ul>'+tags+'</ul>'+
          '<h3>دامنه و حالت‌های مرزی</h3><ul>'+''.join('<li>'+escape(v)+'</li>' for v in p['boundary_checks'])+'</ul>'+
          '<h3>راه‌حل کامل Gemini — بدون کوتاه‌سازی</h3><pre dir="auto">'+escape(q['solution'])+'</pre>'+
          '<h3>توجیه گزینهٔ پاسخ</h3><p dir="auto">'+escape(p['answer_justification'])+'</p>'+
          ('<details><summary>مسیر جایگزین پیشنهادی مدل</summary><p dir="auto">'+escape(p['alternative_route'])+'</p></details>' if p['alternative_route'] else '')+
          '<p>'+comparison_text+'</p>'+
          ('<h3>محدودیت‌های ثبت‌شدهٔ توضیح</h3><ul>'+''.join('<li dir="auto">'+escape(v)+'</li>' for v in limitations)+'</ul>' if limitations else '')+
          '<details><summary>بررسی مستقل دستیار و پاسخ</summary>'+answer+'</details>'+
          '<details><summary>رکورد کامل طراحی، برچسب‌ها و ادعای بررسی مدل (JSON)</summary><pre dir="ltr">'+escape(json.dumps(q,ensure_ascii=False,indent=2))+'</pre></details></article>')
    combined=re.sub(r'<article[^>]*>[\s\S]*?</article>',lambda m:sections.pop(0),qhtml)
    status='<section><h2>وضعیت همهٔ تلاش‌های این نمونه</h2><ul>'+''.join('<li dir="ltr">'+escape(x['id'])+': '+escape(x['state'])+'</li>' for x in outcomes)+'</ul></section>'
    combined=combined.replace('</header>','</header>'+status,1).replace('شناسهٔ R','شناسهٔ P')
    combined=combined.replace('</style>','pre[dir="auto"]{unicode-bidi:plaintext;line-height:2.1;text-align:start}code[dir="ltr"]{display:inline-block;unicode-bidi:isolate}</style>',1)
    output=target/'questions-and-solutions.html';output.write_text(combined,encoding='utf8')
    atomic_json(target/'receipt.json',{'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'questions':len(records),
                'raw_solutions_unabridged':True,'formula_report':rendered,'eligible':False})
    atomic_json(OUT/'review-pointer.json',{'folder':target.name,'sha256':digest,'file':output.name})
    print(json.dumps({'review':str(output),'checked_questions':len(records),'original_generation_outcomes_preserved':True}))


if __name__=='__main__':main()
