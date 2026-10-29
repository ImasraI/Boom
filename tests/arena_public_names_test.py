"""Synthetic account data only; never publish phone-based login identifiers."""
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.auth.database import Base, User, StudentProfile
from app.routers import arena


@pytest.mark.parametrize('username', ['09121112233', '9121112233', '+98 912 111 2233', '۰۹۱۲۱۱۱۲۲۳۳'])
def test_phone_username_is_not_a_public_display_name(username):
    user=SimpleNamespace(id=7,username=username)
    assert arena._public_name(user)=='بازیکن 7'
    assert arena._public_name(user,SimpleNamespace(name='سینا'))=='سینا'
    assert arena._public_name(user,SimpleNamespace(name=username))=='بازیکن 7'


def test_leaderboard_uses_profile_and_hides_phone_fallback():
    engine=create_engine('sqlite://')
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            first=User(id=1,username='9121112233',hashed_password='synthetic',rating=1100)
            second=User(id=2,username='9121112244',hashed_password='synthetic',rating=1050)
            third=User(id=3,username='math_player',hashed_password='synthetic',rating=1020)
            db.add_all([first,second,third]);db.flush()
            db.add(StudentProfile(user_id=1,name='سینا'));db.commit()
            rows=arena.leaderboard(current_user=first,db=db)
            assert [r['username'] for r in rows]==['سینا','بازیکن 2','math_player']
            assert rows[0]['is_you'] is True
            assert arena._arena_name(db,first)=='سینا'
            assert arena._arena_name(db,second)=='بازیکن 2'
    finally:
        engine.dispose()
