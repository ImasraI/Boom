"""Local read-only evidence view for a fully source-checked pilot page."""
import html
import re
from app.rag.exam_corpus import read_json,safe_path,digest,payload_digest


def local_ocr_html(root):
    """Read only local experiments bound to the checked pilot source image."""
    saved=reviewed_page(root)
    if not saved:return None
    esc=lambda value:html.escape(str(value),quote=True)
    expected=digest(saved['image'])
    directory=root/'model-probe/local-ocr'
    cards=[]
    for path in sorted(directory.glob('*/result.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:12]:
        try:safe_path(root,str(path.relative_to(root)))
        except ValueError:continue
        if path.is_symlink() or path.stat().st_size>2_000_000:continue
        row=read_json(path,{})
        if not isinstance(row,dict) or row.get('source_sha256')!=expected:continue
        duration=row.get('elapsed_seconds','pending')
        installation=row.get('model_installation',{})
        details=installation.get('digest','not an Ollama model') if isinstance(installation,dict) else 'unknown'
        cards.append(f'''<article><h2>{esc(row.get('engine'))} · {esc(row.get('model') or row.get('tesseract_version',''))}</h2>
<p>{esc(row.get('state'))} · {esc(duration)} seconds · crop: {esc(row.get('crop') or 'whole page')}</p>
<p>{esc(f"Model download: {row.get('download_bytes',0)/1e9:.2f} / {row.get('download_total_bytes',0)/1e9:.2f} GB") if row.get('state')=='downloading' else ''}</p>
<small>Run: {esc(path.parent.name)} · model digest: {esc(details)}</small>
<p>{esc(row.get('error',''))}</p><pre dir="auto">{esc(row.get('text','No output yet.'))}</pre></article>''')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Local OCR · source comparison</title><style>body{{background:#191513;color:#e8ded3;font:16px system-ui;margin:25px}}a{{color:#d3a28c}}main{{display:grid;grid-template-columns:1fr 1fr;gap:25px}}img{{width:100%;position:sticky;top:20px}}article{{border-bottom:1px solid #634638;padding:10px 0 25px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9}}p,small{{overflow-wrap:anywhere;color:#cdb8a8}}@media(max-width:900px){{main{{display:block}}img{{position:static}}}}</style>
<a href="/">Worker monitor</a> · <a href="/reviewed-page">Checked reference</a><h1>Free local OCR experiments</h1>
<p>Raw candidates, not approved scans. A finished request does not certify source fidelity. No human/scientific review is claimed. Timings are for one selected page/crop and include any model load; they are not bulk throughput.</p>
<main><section>{''.join(cards) or '<p>No pilot results yet.</p>'}</section><section><h2>Original checked source page</h2><img src="/reviewed-page/image" alt="Original source page"><p>Source SHA256: {expected}. Crop coordinates, if present, refer to this whole page. Reload to see completed experiments.</p></section></main></html>'''


def reviewed_page(root):
    from app.rag.exam_scanning import validate_page
    pointer=read_json(root/'reviewed-page.json',{})
    if not isinstance(pointer,dict):return None
    try:
        row=read_json(safe_path(root,pointer.get('record','')), {})
        review=read_json(safe_path(root,pointer.get('review','')), {})
        if not isinstance(row,dict) or not isinstance(review,dict):return None
        data=row.get('data')
        if (not review.get('approved') or review.get('review_kind') not in ('visual','human')
            or review.get('page_coverage_checked') is not True or row.get('coverage')!='full_page'
            or row.get('ok') is not True or validate_page(data)):return None
        actual=[q['number'] for q in data['questions']]
        expected=review.get('expected_question_numbers')
        if (not actual or not isinstance(expected,list) or any(type(n) is not int for n in expected)
            or expected!=actual or sorted(review.get('reviewed_questions',[]))!=sorted(actual)):return None
        if review.get('data_sha256')!=payload_digest(data):return None
        if not re.fullmatch(r'[a-f0-9]{64}',str(row.get('document_id',''))):return None
        if type(row.get('pdf_page')) is not int or row['pdf_page']<1:return None
        image=safe_path(root,row['image'])
        if not image.is_file() or review.get('image_sha256')!=digest(image):return None
        return {'record':row,'review':review,'image':image}
    except (OSError,ValueError,TypeError,KeyError):return None


def review_image(root,option=None):
    saved=reviewed_page(root)
    if not saved:return None
    if option is None:return saved['image']
    for question in saved['record']['data']['questions']:
        for figure in question.get('option_figures',[]):
            if figure.get('label')!=option:continue
            try:
                path=safe_path(root,figure['image'])
                return path if path.is_file() and digest(path)==figure['image_sha256'] else None
            except (OSError,ValueError,TypeError,KeyError):return None
    return None


def efficient_pilot_html(root):
    """A source-bound, read-only quality report; never an approval endpoint."""
    source=reviewed_page(root)
    if not source:return None
    folder=root/'model-probe/efficient-whole-page/gemini-3.5-flash-lite'
    report=read_json(folder/'quality-review.json',{})
    candidate=read_json(folder/'page16-literal-schema.json',{})
    if (not isinstance(report,dict) or not isinstance(candidate,dict)
        or report.get('source_image_sha256')!=source['review']['image_sha256']
        or candidate.get('source_image_sha256')!=source['review']['image_sha256']
        or report.get('reference_data_sha256')!=payload_digest(source['record']['data'])):return None
    esc=lambda value:html.escape(str(value),quote=True)
    checks=''.join('<tr><td>'+esc(c.get('item',''))+'</td><td>'+esc(c.get('result',''))+
        '</td><td>'+esc(c.get('detail',''))+'</td></tr>' for c in report.get('checks',[]) if isinstance(c,dict))
    cards=[]
    for q in candidate.get('data',{}).get('questions',[]):
        options=''.join('<li>'+esc(o.get('text',''))+'</li>' for o in q.get('options',[]) if isinstance(o,dict))
        cards.append('<article><h2>'+esc(q.get('number',''))+'</h2><p>'+esc(q.get('text',''))+
            '</p><ol>'+options+'</ol><p>'+esc(q.get('figure_description',''))+'</p></article>')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flash-Lite OCR quality pilot</title><style>body{{background:#191413;color:#f1e2da;font:15px/1.7 system-ui;margin:0}}main{{max-width:1500px;margin:auto;padding:24px}}a{{color:#e5b7a9}}h1{{font-size:25px}}table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #634638;padding:12px;vertical-align:top}}.warning{{border-left:3px solid #bd6555;padding:16px;background:#30201c}}.layout{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:28px}}img{{width:100%;background:white}}article{{border-bottom:1px solid #634638;padding-bottom:18px}}p,li{{white-space:pre-wrap;overflow-wrap:anywhere}}@media(max-width:850px){{.layout{{grid-template-columns:1fr}}}}</style>
<main><a href="/">Scanner dashboard</a> · <a href="/reviewed-page">Checked source transcription</a>
<h1>{esc(report.get('model'))} · minimal thinking</h1>
<p>One whole-page call: {esc(report.get('whole_page_seconds'))} seconds / {esc(report.get('whole_page_tokens'))} tokens. Focused crop: {esc(report.get('crop_seconds'))} seconds.</p>
<p class="warning">NOT approved for unattended scanning. One selected page; assistant source comparison, no scientific or teacher approval. The reference transcript was not sent to the model. A schema-valid response can still contain source errors.</p>
<table><thead><tr><th>Check</th><th>Result</th><th>Evidence / limitation</th></tr></thead><tbody>{checks}</tbody></table>
<div class="layout"><section dir="rtl"><h2>Raw whole-page candidate</h2>{''.join(cards)}</section><section><h2>Original source image</h2><img src="/reviewed-page/image" alt="Original physics source page"></section></div></main></html>'''


def review_html(root):
    saved=reviewed_page(root)
    if not saved:return None
    esc=lambda value:html.escape(str(value),quote=True)
    row=saved['record'];data=row['data'];cards=[]
    for q in data['questions']:
        options=[]
        for index,value in enumerate(q['options']):
            sequences=q.get('option_sequences')
            value=( '<span dir="ltr">'+esc(', '.join(sequences[index]))+'</span>'
                    if isinstance(sequences,list) and len(sequences)==4 else esc(value))
            image=(f'<img class="option-image" src="/reviewed-page/option-{index+1}" alt="تصویر اصلی گزینه {index+1}">'
                   if q.get('option_figures') else '')
            options.append(f'<li>{value}{image}</li>')
        description=f'<p class="note">{esc(q["figure_description"])}</p>' if q['has_figure'] else ''
        cards.append(f'<article><h2>سؤال {esc(q["number"])}</h2><p>{esc(q["text"])}</p><ol>{"".join(options)}</ol>{description}</article>')
    count=len(data['questions']);corrections=len(row.get('provenance',{}).get('corrections',[]))
    return f'''<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>صفحهٔ بررسی‌شدهٔ OCR</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#191413;color:#f1e2da;font:16px/2 Tahoma,Arial,sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}header{{border-bottom:1px solid #634638;padding-bottom:18px}}h1{{font-size:25px}}h2{{font-size:19px;color:#d4aa91}}.layout{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:30px;margin-top:24px}}.source img{{width:100%;height:auto;background:white}}article{{padding:0 0 24px;margin-bottom:26px;border-bottom:1px solid #634638}}p,li{{white-space:pre-wrap;overflow-wrap:anywhere}}li{{padding:6px 2px}}.note{{color:#c3aa9a;font-size:13px}}.badge{{display:inline-block;padding:5px 12px;border:1px solid #805448;color:#e5b7a9}}a{{color:#e5b7a9}}.option-image{{display:block;max-width:100%;max-height:230px;margin:10px 0;background:white}}@media(max-width:850px){{.layout{{grid-template-columns:1fr}}main{{padding:16px}}}}</style>
<main><header><a href="/">بازگشت به وضعیت اسکن</a><h1>فیزیک · صفحهٔ چاپی {esc(data.get('printed_page',''))} · صفحهٔ PDF {esc(row['pdf_page'])}</h1>
<span class="badge">{count} سؤال کامل · تطبیق تصویری با اصل صفحه</span>
<p class="note">پایه: خروجی ذخیره‌شدهٔ مدل؛ {corrections} اصلاح ثبت‌شده با بررسی تصویری دستیار. این صفحه خروجی کاملاً خودکار نیست. بازبینی علمی یا تأیید انسانی انجام نشده و پاسخ صحیحی استنتاج نشده است.</p></header>
<div class="layout"><section aria-label="رونوشت و شکل‌ها">{''.join(cards)}<p class="note">{esc(data.get('page_text',''))}</p></section>
<section class="source" aria-label="اصل صفحه"><h2>اصل صفحه برای مقایسه</h2><a href="/reviewed-page/image" target="_blank" rel="noopener"><img src="/reviewed-page/image" alt="تصویر کامل و دست‌نخوردهٔ صفحه اصلی"></a></section></div></main></html>'''
