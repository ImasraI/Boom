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
    for (subject,topic),row in evidence.items():
        normalized.setdefault((norm(subject),norm(topic)),[]).append(row)
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
        # Mathematics mocks often use "ریاضی" for a specific calculus topic.
        # Attribute only a uniquely matched exact lesson, never all math topics.
        keys=[(subject,title)]
        if lesson['subject'] in ('حسابان','هندسه','ریاضیات گسسته','آمار و احتمال','گسسته و آمار و احتمال'):
            if sum(norm(n['title'])==title for n in lessons)==1:
                keys.append((norm('ریاضی'),title))
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
