"""Disposable local UI test server; never imports the production database."""
import os
import sys
import tempfile
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
folder = tempfile.mkdtemp(prefix="boom-ui-test-")
os.environ["BOOM_DATABASE_URL"] = "sqlite:///" + str(Path(folder) / "ui.db").replace("\\", "/")
os.environ["SECRET_KEY"] = "test-only-local-secret-not-for-deployment-987654321"
os.environ["APP_ENV"] = "development"
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth.database import Base, engine, SessionLocal, User, StudentProfile, GeneratedMock, MockAttempt
from app.auth.security import get_password_hash
from app.auth.router import router as auth_router
from app.routers import boom_ai, profile, mocks, insights, chat, tasks, arena, challenges
Base.metadata.create_all(engine)
with SessionLocal() as db:
    for i in (1, 2):
        db.add(User(id=i, username=f"912000000{i}", phone=f"912000000{i}", phone_verified=True, hashed_password=get_password_hash("Boom-test-only-42")))
        db.add(StudentProfile(user_id=i, name=f"Test Student {i}", major="ریاضی فیزیک", study_hours="2",
            availability=json.dumps({"wake":"08:00", "daily_hours":{"*":2}, "preferences":{"confidence":{"ریاضی":30,"فیزیک":85}}})))
    qs = [{"_id":i+1,"subject":"ریاضی","topic":"معادله","text":f"حاصل {i+1} + ۱ چیست؟",
           "options":[str(i+2),str(i+3),str(i+4),str(i+5)],"answer":0,"explanation":"جمع دو عدد", "verification_status":"verified"} for i in range(3)]
    db.add(GeneratedMock(id=1, student_id=1, title="آزمون آزمایشی محیط تست", questions=json.dumps(qs,ensure_ascii=False), duration_minutes=5))
    db.commit()
app = FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=["http://127.0.0.1:8444","http://localhost:8444"],allow_methods=["*"],allow_headers=["*"])
for router in (auth_router, boom_ai.router, profile.router, mocks.router, insights.router, chat.router, tasks.router, arena.router, challenges.router):
    app.include_router(router)
# Synthetic question generator for UI interactions; live-provider evaluation is separate.
def fixture_generate(config, current_user, db):
    row = GeneratedMock(student_id=current_user.id,title="آزمون محیط تست",questions=json.dumps(qs,ensure_ascii=False),duration_minutes=5)
    db.add(row);db.commit()
    return {"mock_id":row.id,"title":row.title,"duration_minutes":5,"total_questions":3,"subjects":[{"name":"ریاضی","questions":3,"minutes":5}]}
mocks._generate_reserved_mock = fixture_generate
mocks.consume_ai_use = lambda *a: None
mocks.release_ai_use = lambda *a: None
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8001)


