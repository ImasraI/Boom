"""Reuse shared questions from earlier reviewed Maze scopes without any LLM call."""
from datetime import date

from fastapi import HTTPException

from app.planner import mock_outline
from app.rag import question_bank, weekly_ranked
from app.rag.mock_generation import major_key


def _eligible(student):
    return (major_key(student.get('major') or 'ریاضی فیزیک') == 'riazi'
            and question_bank.grade_number(student.get('grade')) == 12)


def _scope(exam_date):
    if exam_date >= weekly_ranked.today():
        return None
    scope = weekly_ranked.preview(exam_date)
    if not scope.get('available') or scope.get('date') != exam_date.isoformat():
        return None
    return scope


def _questions(db, user_id, scope):
    return question_bank.assemble(db, user_id, scope['plan'], ['ریاضی فیزیک'],
        grade='دوازدهم', shared_only=True, prefer_used=True)


def available(db, user_id, student):
    if not _eligible(student):
        return []
    rows = mock_outline._structured_outlines({'major':'ریاضی فیزیک', 'grade':'دوازدهم',
                                 'testExams':['ماز']}, date(2000, 1, 1))
    dates = sorted({row['date'] for row in rows if row['date'] < weekly_ranked.today()}, reverse=True)
    results = []
    for exam_date in dates[:12]:
        scope = _scope(exam_date)
        if not scope:
            continue
        questions = _questions(db, user_id, scope)
        if questions:
            results.append({'exam_date': scope['date'],
                'title': f"تمرین از مباحث آزمون قبلی ماز — {scope['date']}",
                'total_questions': len(questions), 'difficulty': 'konkur',
                'topics': scope.get('topics', {}), 'source': 'previous_maze'})
    return results


def create(db, user_id, student, exam_date):
    if not _eligible(student):
        raise HTTPException(409, detail='تمرین‌های قبلی ماز برای پایه و رشتهٔ شما آماده نیست.')
    scope = _scope(exam_date)
    questions = _questions(db, user_id, scope) if scope else []
    if not questions:
        raise HTTPException(409, detail={'code':'pool_empty',
            'message':'سؤال‌های قابل استفادهٔ این آزمون قبلی ماز دیگر کافی نیست؛ فهرست را تازه کن.'})
    duration = max(10, sum(row['minutes'] for row in scope['plan']))
    mock = question_bank.create_reused_mock(db, user_id, questions, 'ریاضی فیزیک',
        'دوازدهم', 'konkur', duration)
    mock.title = f"تمرین از مباحث آزمون قبلی ماز — {scope['date']}"
    db.commit()
    return {'mock_id':mock.id, 'title':mock.title, 'duration_minutes':duration,
        'total_questions':len(questions), 'subjects':scope['plan'],
        'source':'previous_maze', 'exam_date':scope['date'], 'fallback':True}
