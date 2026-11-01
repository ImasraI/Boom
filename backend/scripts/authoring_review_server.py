"""Run only local auth + review APIs, without scanner/pool/application lifespan.

From backend: .venv/Scripts/python.exe scripts/authoring_review_server.py
Uses existing local accounts; does not create admins or bypass authentication.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from app.auth.router import router as auth_router
from app.routers.authoring_review import router as review_router

app=FastAPI(title="Local H2 review")
app.include_router(auth_router)
app.include_router(review_router)

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8000)
