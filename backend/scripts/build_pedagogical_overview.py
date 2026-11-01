"""One frozen local sheet across original and recovery runs; retain denominators."""
import hashlib
import html
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.authoring_benchmark import saved_json
from app.rag.exam_corpus import atomic_json,payload_digest
from scripts.prepare_pedagogical_pilot import OUT
from scripts.run_pedagogical_recovery import OUT as RECOVERY


def source(folder):
    ptr=saved_json(folder/'review-pointer.json')
    if ptr['folder']!='review-'+ptr['sha256'] or ptr['file']!='questions-and-solutions.html':
        raise ValueError('Unsafe review reference')
    root=folder/ptr['folder'];m=saved_json(root/'manifest.json');receipt=saved_json(root/'receipt.json')
    if payload_digest(m)!=ptr['sha256']:raise ValueError('Changed source review')
    raw=(root/ptr['file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('Changed review page')
    text=raw.decode('utf8');cards=re.findall(r'<article[^>]*>[\s\S]*?</article>',text)
    if len(cards)!=len(m['records']):raise ValueError('Review card count differs')
    return text,m,receipt,dict(zip((r['spec_id'] for r in m['records']),cards))


def optional_audit(name):
    folder=OUT/name
    if not (folder/'pointer.json').exists():return None
    pointer=saved_json(folder/'pointer.json')
    if not re.fullmatch('[a-f0-9]{64}',pointer['sha256']) or pointer['file']!=pointer['sha256']+'.json':
        raise ValueError('Unsafe audit reference')
    record=saved_json(folder/pointer['file'])
    if payload_digest(record)!=pointer['sha256']:raise ValueError('Changed audit')
    return record


def main():
    base,m1,r1,cards1=source(OUT);_,m2,r2,cards2=source(RECOVERY)
    if set(cards1)&set(cards2):raise ValueError('Ambiguous duplicate review item')
    cards={**cards1,**cards2}
    protocol=saved_json(OUT/saved_json(OUT/'pointer.json')['file'])
    order=[r['spec']['id'] for r in protocol['drafts']]
    if set(cards)!=set(order):raise ValueError('Overview requires all six assigned mechanisms')
    manifest={'schema_version':'0.1','original_review_sha256':payload_digest(m1),
        'recovery_review_sha256':payload_digest(m2),'original_page_sha256':r1['sha256'],
        'recovery_page_sha256':r2['sha256'],'order':order,'eligible':False,
        'builder_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'original_attempt_counts':{'drafted':2,'provider_error':2,'protocol_held':2},
        'recovery_attempt_counts':{'drafted':2},'format_only_projections':2,
        'independent_answer_checks':6,'blind_matches':5,'blind_provider_errors':1,
        'human_scientific_review':False}
    # Derive verification counts from bound reports rather than self-declared constants.
    records=m1['records']+m2['records']
    language=optional_audit('language-policy');originality=optional_audit('originality-screen')
    candidate_shas={r['spec_id']:r['candidate_sha256'] for r in records}
    for report,key in ((language,'audit'),(originality,None)):
        if report is None:continue
        if {r['spec_id'] for r in report['reports']}!=set(candidate_shas):raise ValueError('Incomplete quality audit')
        for row in report['reports']:
            audit=row[key] if key else row
            if audit['candidate_sha256']!=candidate_shas[row['spec_id']]:raise ValueError('Stale quality audit')
    manifest['language_audit_sha256']=payload_digest(language) if language else None
    manifest['originality_screen_sha256']=payload_digest(originality) if originality else None
    matches=sum(bool(r['blind_comparison']) and all(v['blind_solve_state']=='matched' for v in r['blind_comparison']['matrix']) for r in records)
    if matches!=manifest['blind_matches']:raise ValueError('Blind evidence count changed; review overview statement')
    combined=[]
    for i,identifier in enumerate(order,1):
        label=f'G{i:02d}';card=cards[identifier]
        card=re.sub(r'<article id="[^"]+">','<article id="'+label+'">',card,count=1)
        card=re.sub(r'<h2>سؤال .*?</h2>','<h2>سؤال '+str(i)+' <small dir="ltr">('+label+' · '+html.escape(identifier)+')</small></h2>',card,count=1)
        if language:
            holds=next(r['audit']['holds'] for r in language['reports'] if r['spec_id']==identifier)
            badge=('<p><b>بررسی زبان توضیح: </b>'+('بخش‌هایی از توضیح ساختاریافته فارسی نیست؛ '+str(len(holds))+' فیلد علامت‌گذاری شده است.'
                if holds else 'متن از غربال خط فارسی عبور کرد؛ این به معنای تأیید روانی یا درستی متن نیست.')+'</p>')
            card=card.replace('</h2>','</h2>'+badge,1)
        combined.append(card)
    base=re.sub(r'<article[^>]*>[\s\S]*?</article>','',base)
    base=base.replace('</header>', '</header><nav>'+''.join('<a href="#G'+f'{i:02d}'+'">'+str(i)+'</a> · ' for i in range(1,7))+'</nav>',1)
    # Replace original-run-only status with the explicit combined accounting.
    status=('<section><h2>نمونهٔ جدید: شش سازوکار هندسه</h2><p>۶ صورت سؤال از ۸ تلاش تولید: '
        'در اجرای اصلی، ۲ خروجی ساختاریافته، ۲ خطای سرویس و ۲ توقف قالب ثبت شد. '
        'دو توقف قالب فقط اصلاح JSON شده‌اند؛ دو خطای سرویس در اجرای بازیابیِ جداگانه خروجی گرفتند.</p>'
        '<p>کلید هر ۶ سؤال با بررسی مستقل دستیار تطبیق دارد. حل‌کنندهٔ جداگانه برای ۵ سؤال پاسخ یکسان داد؛ '
        'برای سؤال محاطی، سرویس حل‌کننده خروجی معتبر نداد. این‌ها تأیید علمی متخصص نیستند.</p>'
        '<p>نکتهٔ مهم: یادداشت مرزیِ سؤال بازتاب در خروجی مدل اشتباه دارد؛ اصلاح مشخص آن زیر سؤال ثبت شده است. '
        'برچسب‌ها پیشنهادی‌اند و تکرار سازوکار/طبیعی‌بودن سؤال هنوز نیازمند ارزیابی است.</p></section>')
    if originality:
        extra=('<p>غربال شباهت متنی با ۲۴ خروجی قبلی و سؤال‌های همین نمونه: '+str(originality['close_surface_holds'])+
               ' مورد نزدیک به آستانهٔ توقف. این غربال کپیِ لفظی یا تغییر عدد را بررسی می‌کند؛ '
               'شباهت ایدهٔ ریاضی و تازگی سؤال را تأیید نمی‌کند.</p>')
        status=status.replace('</section>',extra+'</section>')
    base=re.sub(r'<section><h2>وضعیت همهٔ تلاش[\s\S]*?</section>',status,base,count=1)
    base=base.replace('</main>',''.join(combined)+'</main>',1) if '</main>' in base else base.replace('</body>',''.join(combined)+'</body>',1)
    if len(re.findall(r'<article\b',base))!=6:raise ValueError('Overview must contain six cards')
    digest=payload_digest(manifest);target=OUT/('combined-review-'+digest);target.mkdir(exist_ok=True)
    path=target/'questions-and-solutions.html'
    if (target/'receipt.json').exists():
        if saved_json(target/'manifest.json')!=manifest:raise ValueError('Frozen overview differs')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=saved_json(target/'receipt.json')['sha256']:
            raise ValueError('Frozen overview changed')
    else:
        atomic_json(target/'manifest.json',manifest);path.write_text(base,encoding='utf8')
        atomic_json(target/'receipt.json',{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'cards':6,'source_render_errors':r1['formula_report']['errors']+r2['formula_report']['errors'],'eligible':False})
    atomic_json(OUT/'combined-review-pointer.json',{'folder':target.name,'file':path.name,'sha256':digest})
    print(str(path))


if __name__=='__main__':main()
