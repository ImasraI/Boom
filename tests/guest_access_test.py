from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.auth import router
from app.auth.database import SessionLocal, User
from app.auth.deps import require_admin
from app.auth.security import decode_token


def test_disabled_guest_never_creates_user(monkeypatch):
    monkeypatch.setattr(router,"get_settings",lambda:SimpleNamespace(PUBLIC_GUEST_ACCESS=False))
    with SessionLocal() as db:
        before=db.query(User).count()
        with pytest.raises(HTTPException) as e:router.guest_login(None,db)
        assert e.value.status_code==404
        assert db.query(User).count()==before


def test_guests_are_distinct_unverified_nonadmin(monkeypatch):
    monkeypatch.setattr(router,"get_settings",lambda:SimpleNamespace(PUBLIC_GUEST_ACCESS=True))
    calls=[];monkeypatch.setattr(router,"rate_limit",lambda *a,**k:calls.append(k))
    with SessionLocal() as db:
        first=router.guest_login(None,db);second=router.guest_login(None,db)
        ids=[int(decode_token(r["access_token"])["sub"]) for r in [first,second]]
        assert ids[0]!=ids[1]
        for id in ids:
            user=db.get(User,id)
            assert user.phone is None and not user.phone_verified and not user.is_admin
            assert user.username.startswith("guest_")
            with pytest.raises(HTTPException) as e:require_admin(user)
            assert e.value.status_code==403
        assert all(c["limit"]==5 and c["window_s"]==3600 for c in calls)


def test_rate_limit_stops_creation(monkeypatch):
    monkeypatch.setattr(router,"get_settings",lambda:SimpleNamespace(PUBLIC_GUEST_ACCESS=True))
    def refuse(*a,**k):raise HTTPException(status_code=429)
    monkeypatch.setattr(router,"rate_limit",refuse)
    with SessionLocal() as db:
        before=db.query(User).count()
        with pytest.raises(HTTPException):router.guest_login(None,db)
        assert db.query(User).count()==before
