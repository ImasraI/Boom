"""Export an answer-bearing local inspector; never alter frozen review pages."""
import hashlib
import html
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rag.exam_corpus import payload_digest

ROOT = Path(__file__).resolve().parents[1] / 'data/authoring_work/development-benchmark-v1'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def child(name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9-]+', name):
        raise ValueError('Invalid saved revision name')
    return ROOT / name


def articles(document):
    result = {}
    for inner in re.findall(r'<article[^>]*>([\s\S]*?)</article>', document):
        alias = re.search(r'\((R\d{2})\)</small>', inner)
        if not alias or alias[1] in result:
            raise ValueError('Missing or repeated display alias')
        result[alias[1]] = inner
    return result


def main():
    pointer = read(ROOT / 'served-latest-preview.json')
    source = child(pointer['source_folder'])
    manifest = read(source / 'manifest.json')
    if payload_digest(manifest) != pointer['manifest_sha256']:
        raise ValueError('Changed preview manifest')
    binding_pointer = read(ROOT / 'review-pointer.json')
    binding = read(child(binding_pointer['folder']) / 'binding.json')
    if payload_digest(binding) != binding_pointer['binding_sha256']:
        raise ValueError('Changed review binding')
    if manifest['parent_review_binding_sha256'] != binding_pointer['binding_sha256']:
        raise ValueError('Preview and review differ')
    status = read(source / 'status.json')
    for name, digest in status['page_sha256'].items():
        if Path(name).name != name:
            raise ValueError('Unsafe page reference')
        if hashlib.sha256((source / 'pages' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Changed frozen page')
    q_html = (source / 'pages/questions.html').read_text(encoding='utf8')
    a_html = (source / 'pages/solutions.html').read_text(encoding='utf8')
    questions, answers = articles(q_html), articles(a_html)
    records = {r['alias']: r for r in binding['records']}
    deltas = {r['alias']: r for r in manifest['deltas']}
    if set(questions) != set(answers) or set(questions) != set(records):
        raise ValueError('Question/answer/metadata aliases differ')
    fields = {'givens': 'داده‌ها', 'unknown': 'خواستهٔ سؤال', 'domains': 'دامنه و شرط‌ها',
              'essential_insight': 'ایدهٔ کلیدی پیشنهادی مدل',
              'structural_departure': 'ادعای مدل دربارهٔ تفاوت ساختاری',
              'tempting_wrong_route': 'مسیر اشتباهِ وسوسه‌کنندهٔ پیشنهادی مدل'}
    escape = lambda value: html.escape(str(value), quote=True)
    cards = []
    for alias, question in questions.items():
        row = records[alias]
        if payload_digest(row['candidate']) != row['candidate_sha256']:
            raise ValueError('Changed raw candidate')
        if deltas[alias]['original_candidate_sha256'] != row['candidate_sha256']:
            raise ValueError('Stale presentation delta')
        group = 'پایه؛ بدون راهنمای طراحی اضافه' if row['arm'] == 'baseline' else 'همراه راهنمای طراحی'
        notes = ''.join('<dt>'+escape(label)+'</dt><dd dir="auto">'+escape(row['candidate']['design'][key])+'</dd>' for key,label in fields.items())
        changes = deltas[alias]['changes']
        corrections = '<ul>'+''.join('<li dir="auto">'+escape(c)+'</li>' for c in changes)+'</ul>' if changes else '<p>اصلاح نمایشی ثبت نشده است.</p>'
        answer = re.sub(r'<h2>[\s\S]*?</h2>', '<h2>پاسخ و بررسی</h2>', answers[alias], count=1)
        cards.append('<article id="'+alias+'">'+question+'<hr>'+answer+
            '<h3>اطلاعات طراحی و برچسب‌ها</h3><p>گروه تولید: '+group+'</p>'+
            '<p>برچسب‌های رسمیِ روش حل و شناسه‌های مبحثِ کتاب: در این خروجی ثبت نشده‌اند؛ هنوز نیازمند برچسب‌گذاری و کالیبراسیون‌اند.</p>'+
            '<p>یادداشت‌های زیر ادعای مدل هستند؛ تأیید انسانیِ تازگی یا روش حل محسوب نمی‌شوند.</p><dl>'+notes+'</dl>'+
            '<details><summary>اصلاحات و شناسهٔ نسخه</summary>'+corrections+'<p dir="ltr">'+escape(row['candidate_sha256'])+'</p></details>'+
            '<section class="author-solution"><h3>راه‌حل کامل Gemini</h3><p>متن کامل فیلد solution در پاسخ ذخیره‌شدهٔ مدل؛ بدون کوتاه‌سازی یا بازنویسی. این توضیحِ بازگشتی است، نه استدلال داخلی و پنهان مدل.</p><pre dir="auto">'+escape(row['candidate']['solution'])+'</pre></section></article>')
    document = re.sub(r'<article[^>]*>[\s\S]*?</article>', lambda m: cards.pop(0), a_html)
    document = document.replace('</head>', '<style>dt{font-weight:700;margin-top:1rem}dd{margin:0;padding:.5rem 0;white-space:pre-wrap;overflow-wrap:anywhere;unicode-bidi:plaintext}hr{margin:2rem 0;opacity:.25}details{margin:1rem 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head>')
    banner = '<aside><h1>سؤال، پاسخ و اطلاعات طراحی — نسخهٔ آشکار</h1><p>۲۴ پیش‌نویس آزمایشی؛ نویسنده: Gemini gemini-3.6-flash. پاسخ‌ها و گروه تولید در این صفحه آشکارند؛ بازخورد بر این صفحه کور محسوب نمی‌شود. بررسی‌های ریاضیِ دستیار، تأیید علمیِ متخصص نیستند.</p></aside>'
    document = re.sub(r'(<body[^>]*>)', lambda m: m[1]+banner, document, count=1)
    digest = hashlib.sha256(document.encode()).hexdigest()
    target = ROOT / ('detailed-inspector-'+digest)
    target.mkdir(exist_ok=True)
    output = target / 'questions-answers-design.html'
    if output.exists() and output.read_text(encoding='utf8') != document:
        raise ValueError('Inspector revision changed')
    output.write_text(document, encoding='utf8')
    receipt = {'sha256': digest, 'questions': len(records), 'parent_preview': pointer['manifest_sha256'],
               'formal_taxonomy_tags_assigned': False, 'blind_review': False, 'human_approved': False}
    (target / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    print(json.dumps({'output': str(output), 'questions': len(records), 'sha256': digest}))


if __name__ == '__main__':
    main()
