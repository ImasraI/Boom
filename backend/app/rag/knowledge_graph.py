"""Cached, book-sourced curriculum with strictly user-scoped mastery evidence."""
from __future__ import annotations

from app.rag.book_curriculum import load_catalog, norm
from app.rag.konkur_format import major_key


def _stats(rows):
    attempted=sum(row.get('attempted',0) for row in rows)
    correct=sum(row.get('correct',0) for row in rows)
    return {'attempted':attempted,'correct':correct,
            'wrong':sum(row.get('wrong',0) for row in rows),
            'accuracy':round(correct/attempted,3) if attempted else None}


def curriculum_lookup(major, catalog=None):
    """Resolve only exact book titles, allowing unambiguous generic math labels."""
    catalog = load_catalog() if catalog is None else catalog
    lessons = [n for n in catalog.get('nodes', []) if major_key(major) in n.get('majors', [])]
    lookup = {(norm(n['subject']), norm(n['title'])): (n['subject'], n['title']) for n in lessons}
    math = {'حسابان', 'هندسه', 'ریاضیات گسسته', 'آمار و احتمال', 'گسسته و آمار و احتمال'}
    candidates = {}
    for node in lessons:
        if node['subject'] in math:
            candidates.setdefault(norm(node['title']), set()).add((node['subject'], node['title']))
    for title, matches in candidates.items():
        if len(matches) == 1:
            lookup.setdefault((norm('ریاضی'), title), next(iter(matches)))
    return lookup


def build_graph(major: str, evidence=None, read_keys=None) -> dict:
    """Opening a graph never calls an LLM or consults another user's records."""
    catalog=load_catalog()
    evidence=evidence or {}
    reads={(norm(subject),norm(topic)) for subject,topic in (read_keys or [])}
    lessons=[node for node in catalog.get('nodes',[]) if major_key(major) in node.get('majors',[])]
    subjects=list(dict.fromkeys(node['subject'] for node in lessons))
    # Exact normalized titles only: arbitrary mock topic strings are not proof
    # that a particular textbook lesson has been studied or mastered.
    normalized={}
    lookup = curriculum_lookup(major, catalog)
    for (subject,topic),row in evidence.items():
        canonical = lookup.get((norm(subject), norm(topic)))
        if canonical:
            normalized.setdefault(tuple(map(norm, canonical)),[]).append(row)
    reads.update(tuple(map(norm, lookup[key])) for key in list(reads) if key in lookup)
    nodes=[]; edges=[]
    for subject in subjects:
        key=norm(subject)
        rows=[row for (s,_),items in normalized.items() if s==key for row in items]
        stat=_stats(rows)
        opened=any(s==key for s,_ in reads) or stat['attempted']>0
        nodes.append({'id':'subject:'+key,'kind':'subject','subject':subject,'title':subject,
                      'year':0,'importance':5,'opened':opened,'available':True,**stat})
    for lesson in lessons:
        subject=norm(lesson['subject']); title=norm(lesson['title'])
        keys=[(subject,title)]
        stat=_stats([row for key in keys for row in normalized.get(key,[])])
        opened=any(key in reads for key in keys) or stat['attempted']>0
        nodes.append({**lesson,'kind':'lesson','opened':opened,'available':False,**stat})
        edges.append({'source':'subject:'+subject,'target':lesson['id'],'kind':'contains'})
    by_id={node['id']:node for node in nodes}
    edges += [edge for edge in catalog.get('edges',[]) if edge['source'] in by_id and edge['target'] in by_id]
    incoming={}
    for edge in edges:
        if edge['kind']=='prerequisite': incoming.setdefault(edge['target'],[]).append(edge['source'])
    for node in nodes:
        if node['kind']=='lesson':
            node['available']=node['opened'] or all(by_id[parent]['opened'] for parent in incoming.get(node['id'],[]))
    books=sorted({source['book'] for lesson in lessons for source in lesson.get('sources',[])})
    return {'major':major,'years':[10,11,12,0],'nodes':nodes,'edges':edges,
            'curriculum':{'source':'book_ocr','books':books,'book_count':len(books),
                          'lesson_count':len(lessons),'complete':bool(catalog.get('complete')),
                          'updated_at':catalog.get('updated_at'),
                          'status':'ready' if lessons else 'missing_books',
                          'prerequisites':'model_estimate', 'importance':'model_estimate'},
            'legend':{'importance':'اهمیت و پیش‌نیازها: برآورد مدل از مباحث کتاب',
                      'mastery':'رنگ گره بازشده = دقت پاسخ‌های ثبت‌شدهٔ شما',
                      'locked':'گره خاکستری = هنوز مطالعه یا پاسخی ثبت نشده'}}
