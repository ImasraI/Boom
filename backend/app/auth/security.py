from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

# bcrypt (salted, slow) for all NEW hashes; sha256_crypt stays only so
# accounts created before the switch can still log in and get upgraded.
pwd_context = CryptContext(schemes=["bcrypt", "sha256_crypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    if isinstance(password, str):
        # bcrypt operates on at most 72 bytes; truncate deterministically.
        password_bytes = password.encode('utf-8')[:72]
        password = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


def needs_rehash(hashed_password: str) -> bool:
    """True when `hashed_password` uses a legacy scheme (login should upgrade)."""
    return pwd_context.needs_update(hashed_password)


# app/auth/security.py

from datetime import datetime, timedelta, timezone  # add timezone


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        print(f"JWT decode error: {e}")
        return None
