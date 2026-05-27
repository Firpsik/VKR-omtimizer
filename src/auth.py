import os
import secrets
from typing import Optional

from fastapi import Cookie, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from sqlalchemy import text

from src.db import get_engine

SECRET_KEY = os.environ.get("AUTH_SECRET_KEY") or secrets.token_hex(32)
SESSION_COOKIE = "asop_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeSerializer(SECRET_KEY, salt="asop-session")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except Exception:
        return False


def make_session_token(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> Optional[int]:
    try:
        data = _serializer.loads(token)
        return int(data["uid"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


def load_user(user_id: int) -> Optional[dict]:
    with get_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT user_id, email, display_name, is_admin, is_demo
              FROM mp.users WHERE user_id = :uid
        """), {"uid": user_id}).fetchone()
    if not row:
        return None
    return {
        "user_id": row[0],
        "email": row[1],
        "display_name": row[2],
        "is_admin": row[3],
        "is_demo": row[4],
    }


def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    uid = read_session_token(token)
    if uid is None:
        return None
    return load_user(uid)


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


def require_writeable_user(request: Request) -> dict:
    user = require_user(request)
    if user.get("is_demo"):
        raise HTTPException(403, detail="Демо-режим: изменения отключены")
    return user


def find_user_by_email(email: str) -> Optional[dict]:
    with get_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT user_id, email, password_hash, display_name, is_admin, is_demo
              FROM mp.users WHERE LOWER(email) = LOWER(:e)
        """), {"e": email}).fetchone()
    if not row:
        return None
    return {
        "user_id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "display_name": row[3],
        "is_admin": row[4],
        "is_demo": row[5],
    }


def create_user(email: str, password: str, display_name: Optional[str] = None) -> int:
    if find_user_by_email(email):
        raise ValueError(f"Пользователь {email} уже существует")
    with get_engine().begin() as conn:
        row = conn.execute(text("""
            INSERT INTO mp.users (email, password_hash, display_name)
            VALUES (:e, :h, :n)
            RETURNING user_id
        """), {"e": email.lower(), "h": hash_password(password), "n": display_name}).fetchone()
    return int(row[0])


def reset_demo_password(new_password: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE mp.users SET password_hash = :h WHERE is_demo = TRUE
        """), {"h": hash_password(new_password)})


def delete_user(user_id: int) -> None:
    engine = get_engine()
    with engine.connect() as conn, conn.begin():
        conn.execute(text("DELETE FROM mp.users WHERE user_id = :uid"), {"uid": user_id})