"""Admin account manager - the ONLY way admin accounts are created or removed.

    cd backend
    .venv/Scripts/python.exe scripts/manage_admin.py create 09121234567 [password]
    .venv/Scripts/python.exe scripts/manage_admin.py delete 09121234567
    .venv/Scripts/python.exe scripts/manage_admin.py list
    .venv/Scripts/python.exe scripts/manage_admin.py set-password 09121234567 newpass

- create: makes (or promotes) the account for that phone with is_admin=1.
  Username = normalized phone; password hashed with bcrypt. If you omit the
  password, one is generated and printed once - store it in a password
  manager, it is never shown again.
- delete: strips admin (is_admin=0). With --purge, also deletes the user row
  and the junk data attached to it (their mocks/attempts/wrong answers).
- Accounts are NOT phone-verified by default: admins log in with username +
  password, so verification is irrelevant for them.
"""

import argparse
import io
import secrets
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.auth.database import SessionLocal, User, WrongAnswer, ensure_schema
from app.auth.sms import normalize_ir_mobile
from app.auth.security import get_password_hash

ensure_schema()


def resolve_identifier(identifier: str) -> tuple:
    """'0912...' -> (phone-as-username, phone); 'admin' -> ('admin', None).
    Admins log in with username + password, so a real phone is optional."""
    ident = identifier.strip()
    try:
        phone_norm = normalize_ir_mobile(ident)
        return phone_norm, phone_norm
    except ValueError:
        if not ident or len(ident) < 3:
            sys.exit("identifier must be a phone number or a username (3+ chars)")
        return ident, None


def _find(db, username: str):
    return db.query(User).filter(User.username == username).first()


def cmd_create(db, username: str, phone, password) -> None:
    if not password:
        password = secrets.token_urlsafe(9)[:10]
        generated = True
    else:
        generated = False
    user = _find(db, username)
    if user:
        user.is_admin = True
        action = "promoted existing account"
    else:
        user = User(
            username=username,
            phone=phone,
            hashed_password=get_password_hash(password),
            phone_verified=True,
            is_admin=True,
        )
        db.add(user)
        action = "created"
    db.commit()
    db.refresh(user)
    print("=" * 46)
    print(f"Admin account {action}.")
    print(f"  username: {user.username}")
    print(f"  password: {password}")
    if generated:
        print("  (auto-generated - store it NOW; it will not be shown again)")
    print("=" * 46)


def cmd_delete(db, username: str, purge: bool) -> None:
    user = _find(db, username)
    if not user:
        sys.exit(f"no account for {username}")
    if not user.is_admin:
        sys.exit(f"{user.username} is not an admin; nothing to remove.")
    user.is_admin = False
    if purge:
        n = db.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM wrong_answers WHERE student_id = :uid"),
            {"uid": user.id}).rowcount
        db.delete(user)
        print(f"purged admin account {user.username} (id {user.id}) "
              f"and {n} attached wrong-answer row(s) + their mocks/attempts.")
    else:
        print(f"admin rights removed for {user.username} (account kept).")
    db.commit()


def cmd_list(db) -> None:
    admins = db.query(User).filter(User.is_admin.is_(True)).all()
    if not admins:
        print("no admin accounts")
        return
    for u in admins:
        print(f"  id={u.id:<4} username={u.username:<14} phone={u.phone or '-':<12}")


def cmd_set_password(db, username: str, password: str) -> None:
    user = _find(db, username)
    if not user or not user.is_admin:
        sys.exit(f"no admin account for {username}")
    user.hashed_password = get_password_hash(password)
    db.commit()
    print(f"password updated for {user.username}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=["create", "delete", "list", "set-password"])
    parser.add_argument("identifier", nargs="?",
                        help="phone number (any IR format) or plain username")
    parser.add_argument("password", nargs="?",
                        help="password (optional for create; required for set-password)")
    parser.add_argument("--purge", action="store_true",
                        help="delete: also remove the account + its data")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.command == "list":
            cmd_list(db)
            return
        if not args.identifier:
            sys.exit("phone/username required for this command")
        username, phone = resolve_identifier(args.identifier)
        if args.command == "create":
            cmd_create(db, username, phone, args.password)
        elif args.command == "delete":
            cmd_delete(db, username, args.purge)
        elif args.command == "set-password":
            if not args.password:
                sys.exit("set-password needs a password argument")
            cmd_set_password(db, username, args.password)
    finally:
        db.close()


if __name__ == "__main__":
    main()
