"""Current exam inventory, deliberately separate from historical pool totals."""
import json
from sqlalchemy import select
from app.auth.database import GeneratedMock
from app.rag import weekly_ranked, pool_core
from app.rag.exam_blueprint import matches_plan


def inventory(db):
    current = weekly_ranked.preview()
    results = []
    for major in pool_core.STARTER_MAJORS:
        for grade in pool_core.STARTER_GRADES:
            supported = major == 'riazi' and grade == 'دوازدهم'
            mapped = supported and current['available']
            count = 0
            if mapped:
                rows = db.scalars(select(GeneratedMock).where(
                    GeneratedMock.major == pool_core.CANONICAL_MAJOR[major],
                    GeneratedMock.grade == grade, GeneratedMock.status == 'pending_use',
                    GeneratedMock.student_id == 0))
                for mock in rows:
                    if (pool_core._ready_stock(db, mock.questions)
                            and matches_plan(json.loads(mock.questions), current['plan'], grade, [])):
                        count += 1
            results.append({'major': pool_core.CANONICAL_MAJOR[major], 'grade': grade,
                'exam_date': current.get('date') if supported else None,
                'scope': current.get('scope') if supported else None,
                'mapping_ready': bool(mapped), 'ready_booklets': count,
                'questions_per_booklet': 10,
                'reason': '' if mapped else current.get('code', 'scope_unmapped') if supported else 'grade_major_scope_not_integrated'})
    return results
