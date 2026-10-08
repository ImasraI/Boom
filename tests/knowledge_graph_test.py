import json
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.auth.database import Base, GeneratedMock, MockAttempt, StudentProfile, Subject, StudySession, User
from app.routers.insights import knowledge_graph


def test_user_graph_opens_read_nodes_and_keeps_prerequisites_locked(monkeypatch):
    from app.rag import knowledge_graph as graph_module
    nodes=[{'id':name,'title':title,'subject':'حسابان','year':11,'importance':4,'majors':['riazi'],
            'sources':[{'book':'حسابان 1 خیلی سبز','page':7,'quote':title}]}
           for name,title in [('functions','تابع‌ها'),('algebra','معادلات درجه دوم'),('limits','حد و پیوستگی')]]
    monkeypatch.setattr(graph_module,'load_catalog',lambda:{'nodes':nodes,'edges':[
        {'source':'functions','target':'limits','kind':'prerequisite'},
        {'source':'algebra','target':'limits','kind':'prerequisite'}],'complete':True})
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(id=1, username="graph-user", hashed_password="x")
        db.add(user)
        db.add(StudentProfile(user_id=1, major="ریاضی فیزیک"))
        db.add(Subject(id=1, name="حسابان"))
        mock = GeneratedMock(
            student_id=1,
            title="limits",
            questions=json.dumps([
                {"_id": 1, "subject": "حسابان", "topic": "تابع‌ها", "answer": 0, "verification_status": "verified"},
                {"_id": 2, "subject": "حسابان", "topic": "تابع‌ها", "answer": 0, "verification_status": "verified"},
            ]),
        )
        db.add(mock)
        db.flush()
        db.add(MockAttempt(student_id=1, mock_id=mock.id, answers=json.dumps({"1": 0, "2": 1})))
        db.add(StudySession(
            student_id=1,
            subject_id=1,
            subject_name="حسابان",
            topic_name="تابع‌ها",
            started_at=__import__("datetime").datetime.utcnow(),
            completion_status="completed",
        ))
        db.commit()

        graph = knowledge_graph(SimpleNamespace(id=1), db)
        functions = next(node for node in graph["nodes"] if node["title"] == "تابع‌ها")
        limits = next(node for node in graph["nodes"] if node["title"] == "حد و پیوستگی")
        assert functions["opened"] is True
        assert functions["accuracy"] == 0.5
        assert limits["opened"] is False
        assert limits["available"] is False
        assert any(edge["kind"] == "prerequisite" for edge in graph["edges"])
        assert functions['sources'][0]['page']==7
        stranger=knowledge_graph(SimpleNamespace(id=2),db)
        assert all(not n['opened'] and n['attempted']==0 for n in stranger['nodes'])
