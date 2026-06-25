"""
Аутентификация: пароли, сессии, rate limiting, зависимости FastAPI.
"""

import re
import secrets
import time
from collections import defaultdict
from datetime import timedelta, datetime

import bcrypt as _bcrypt
from fastapi import HTTPException, Header, Request

from db import get_db

SESSION_EXPIRE_HOURS = 24
VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_]+$")

# Rate limiting: не более 10 попыток входа с одного IP за 60 секунд
_login_attempts: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 10


def verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def check_rate_limit(request: Request):
    ip = request.headers.get("X-Forwarded-For", "")
    ip = ip.split(",")[0].strip() if ip else (request.client.host if request.client else "unknown")
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(429, "Слишком много попыток входа. Попробуйте через минуту.")
    _login_attempts[ip].append(now)


def validate_id(user_id: str) -> str:
    id_clean = user_id.strip()
    if not id_clean or not VALID_ID_PATTERN.match(id_clean):
        raise HTTPException(400, "Некорректный идентификатор")
    return id_clean


def create_session(user_id: int, user_type: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)

    with get_db() as conn:
        # Заодно подчищаем все протухшие сессии, чтобы таблица не росла
        conn.execute("DELETE FROM sessions WHERE expires_at <= %s", (datetime.now(),))
        conn.execute("DELETE FROM sessions WHERE user_id = %s AND user_type = %s", (user_id, user_type))
        conn.execute("""
            INSERT INTO sessions (token, user_id, user_type, expires_at)
            VALUES (%s, %s, %s, %s)
        """, (token, user_id, user_type, expires_at))
    return token


def verify_session(token: str):
    if not token:
        return None

    current_time = datetime.now()
    with get_db() as conn:
        cur = conn.execute("SELECT user_id, user_type, expires_at FROM sessions WHERE token = %s", (token,))
        row = cur.fetchone()
        if not row:
            return None

        user_id, user_type, expires_at = row
        if expires_at <= current_time:
            conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
            return None

        return (user_id, user_type)


async def require_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")

    token = authorization.split(" ", 1)[1]
    session = verify_session(token)
    if not session:
        raise HTTPException(401, "Неверный или просроченный токен")
    return session


async def require_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")
    token = authorization.split(" ", 1)[1]
    session = verify_session(token)
    if not session:
        raise HTTPException(401, "Неверный или просроченный токен")
    user_id, user_type = session
    if user_type != "admin":
        raise HTTPException(403, "Доступ запрещён")
    return user_id
