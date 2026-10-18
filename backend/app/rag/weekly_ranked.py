"""Rolling, book-backed Maze scope for grade-12 math/physics ranked games."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from app.planner.mock_outline import next_mock_outline
from app.planner.resources import _norm, _subject
from app.rag import exam_blueprint as blueprint
from app.rag.book_curriculum import load_catalog
from app.rag.konkur_format import KONKUR_SUBJECTS, resize_plan


def exam_day(instant=None):
    try: zone=ZoneInfo('Asia/Tehran')
    except ZoneInfoNotFoundError: zone=timezone(timedelta(hours=3,minutes=30))
    instant = instant or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone).date()


def today():
    return exam_day()


def topic_matches(topic, title):
    def words(value):
        value = _norm(value).replace('ۀ','ه').replace('ة','ه').replace('معادلات','معادله').replace('توابع','تابع')
        return {w for w in re.findall(r'\w+',value) if len(w)>1 and not w.isdigit() and w not in
                {'فصل','صفحه','های','مبحث','آشنایی','با','بخش','درس','کاربردها','کاربرد'}}
    a,b = words(topic),words(title)
    if _norm(topic)=='تابع' and re.search('مشتق|مثلث|سینوس|کسینوس|حد|لگاریتم|نمایی|مجانب|اکسترمم|یکنوایی',_norm(title)):
        return False
    if 'نظریه اعداد' in _norm(topic):
        return a <= b or any(t in _norm(title) for t in ('استدلال','بخش پذیری','بخش‌پذیری'))
    return bool(a and b and (a <= b or b <= a))


def preview(as_of=None):
    outline = next_mock_outline({'major':'ریاضی فیزیک','grade':'دوازدهم','testExams':['ماز']},as_of or today())
    if not outline:
        return {'available':False,'code':'maze_schedule_missing','message':
            'در برنامهٔ مازِ پردازش‌شده آزمون آینده‌ای نیست؛ برنامهٔ جدید را استخراج و تأیید کنید.',
            'plan':[],'questions':10,'grade':'دوازدهم','major':'riazi'}
    catalog = load_catalog()
    plan = resize_plan(KONKUR_SUBJECTS['riazi'],10)
    missing = []
    for row in plan:
        row.update(major='riazi',book_grounded=True,full_mock=True)
        row['topics'] = outline['topics'].get(row['name'],[])
        nodes = blueprint.lessons_for(row,'دوازدهم',catalog=catalog)
        sections = [s for s in outline.get('sections',[]) if _subject(s['subject'])==row['name']]
        selected = []
        scopes = {}
        for section in sections or [{'topics':row['topics']}]:
            for topic in section['topics']:
                matching = [node for node in nodes if (not section.get('year') or node.get('year') in (0,section['year']))
                    and (not section.get('subject') or _subject(section['subject'])!='ریاضی' or
                         blueprint.math_branch(section['subject']) == blueprint.math_branch(node['subject'],node['title']))
                    and (topic=='کل کتاب' or topic_matches(topic,node['title']))]
                if not matching: missing.append({'subject':row['name'],'topic':topic,'year':section.get('year')})
                selected.extend(matching)
                for node in matching: scopes.setdefault(node['id'],[]).append(section.get('quote',topic))
        row['curriculum_ids'] = sorted({n['id'] for n in selected})
        row['maze_scope'] = scopes
        if row['name'] == 'ریاضی' and selected:
            # Cover every math branch present in this exam, then assign any
            # remaining slot to the branch with the largest Konkur weight.
            from app.rag.konkur_format import RIAZI_MATH_BLUEPRINT
            present = {blueprint.math_branch(n['subject'], n['title']) for n in selected}
            branches = {b: 1 for b in RIAZI_MATH_BLUEPRINT if b in present}
            for _ in range(max(0, row['questions'] - len(branches))):
                branch = max(branches, key=lambda b: RIAZI_MATH_BLUEPRINT[b] / (branches[b] + 1))
                branches[branch] += 1
            row['branches'] = branches
        if not row['topics'] or not selected:
            missing.append({'subject':row['name'],'topic':'مبحث مستند موجود نیست'})
    signature = {'date':outline['date'].isoformat(),'document':outline['document'],
                 'source':outline.get('source_digest'),'topics':outline['topics'],
                 'ids':{r['name']:r['curriculum_ids'] for r in plan},
                 'boundaries':{r['name']:r['maze_scope'] for r in plan},
                 'allocations':{r['name']:r.get('branches') for r in plan}}
    scope = hashlib.sha256(json.dumps(signature,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    for row in plan: row['weekly_ranked_scope'] = scope
    return {'available':not missing,'code':'maze_topics_unmapped' if missing else '',
        'message':'مبحث‌های برنامه باید به فصل‌های مستند کتاب متصل شوند.' if missing else '',
        'date':outline['date'].isoformat(),'document':outline['document'],'source_page':outline.get('source_page'),
        'topics':outline['topics'],'missing':missing,'plan':plan,'scope':scope,
        'questions':10,'grade':'دوازدهم','major':'riazi'}


def require_plan(as_of=None):
    result = preview(as_of)
    if not result['available']:
        raise HTTPException(409,detail={'code':result['code'],'message':result['message'],'missing':result.get('missing',[])})
    return result['plan']


def available_preview(db, user_id, grade='', as_of=None):
    """Prefer the upcoming exam, then complete stock from reviewed older scopes.

    This only checks availability: it neither claims papers nor marks questions
    used. Assembly keeps reports, verification, curriculum and scope checks.
    """
    from app.planner.mock_outline import _structured_outlines
    from app.rag import question_bank
    current = preview(as_of)
    result = {**current, 'fallback': False, 'requested_date': current.get('date'),
              'stock_available': False}
    if not current['available'] and not current.get('date'):
        return result

    def ready(candidate):
        return bool(question_bank.assemble(db, user_id, candidate['plan'], ['ریاضی فیزیک'],
                                          grade=grade or 'دوازدهم', shared_only=True, prefer_used=False))

    if current['available'] and ready(current):
        return {**result, 'stock_available': True}
    student = {'major':'ریاضی فیزیک','grade':'دوازدهم','testExams':['ماز']}
    cutoff = date.fromisoformat(current['date'])
    dates = sorted({row['date'] for row in _structured_outlines(student, date(2000,1,1))
                    if row['date'] < cutoff}, reverse=True)
    seen = {current['scope']}
    for previous_date in dates:
        previous = preview(previous_date)
        if (not previous['available'] or previous.get('date') != previous_date.isoformat()
                or previous.get('scope') in seen):
            continue
        seen.add(previous['scope'])
        if ready(previous):
            return {**previous, 'fallback': True, 'stock_available': True,
                    'requested_date': current['date'],
                    'message': 'سؤال‌های آزمون آینده هنوز کافی نیست؛ این مسابقه از نسخهٔ تأییدشدهٔ آزمون قبلی ماز است.'}
    return {**result, 'message': 'برای آزمون آینده یا نسخه‌های پیشین ماز هنوز ۱۰ سؤال تأییدشدهٔ سازگار آماده نیست.'}


def prepare_config(config):
    if config.get('kind')!='weekly_ranked': return config
    plan = require_plan()
    return {**config,'weekly_plan':plan,'weekly_scope':plan[0]['weekly_ranked_scope']}
