"""Guest creation is retired and existing guest tokens cannot authorize requests."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import router as auth
from app.auth.database import SessionLocal, User
from app.auth.security import create_access_token, get_password_hash


def test_guest_routes_cannot_create_accounts():
    app = FastAPI()
    app.include_router(auth.router)
    with SessionLocal() as db, TestClient(app) as client:
        before = db.scalar(select(func.count(User.id)))
        assert client.get("/api/auth/guest-status").status_code == 404
        assert client.post("/api/auth/guest").status_code == 404
        assert db.scalar(select(func.count(User.id))) == before


def test_existing_guest_token_and_password_are_rejected(monkeypatch):
    app = FastAPI()
    app.include_router(auth.router)
    monkeypatch.setattr(auth, "rate_limit", lambda *args, **kwargs: None)
    password = "synthetic-guest-password"
    with SessionLocal() as db, TestClient(app) as client:
        guest = User(username="guest_" + "0" * 32, hashed_password=get_password_hash(password))
        db.add(guest)
        db.commit()
        token = create_access_token({"sub": str(guest.id)})
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        assert client.post("/api/auth/login", data={
            "username": guest.username, "password": password,
        }).status_code == 401
        assert db.get(User, guest.id) is not None
