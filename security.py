# security.py
import os
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from db import get_conn
from models import UserPublic

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
ACCESS_TOKEN_EXPIRES_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRES_MIN", "60"))

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(raw: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(raw.encode("utf-8"), salt).decode("utf-8")


def verify_password(raw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(sub: str, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MIN)).timestamp())}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


async def _load_user_by_email(conn: AsyncConnection, email: str) -> Optional[UserPublic]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("select id::text, email, name from users where lower(email)=lower(%s)", (email,))
        row = await cur.fetchone()
        return UserPublic.model_validate(row) if row else None


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: AsyncConnection = Depends(get_conn),
) -> UserPublic:
    if not creds:
        raise HTTPException(401, "Authorization required")
    payload = decode_token(creds.credentials)
    email = payload.get("sub")
    if not email:
        raise HTTPException(401, "Invalid token payload")
    user = await _load_user_by_email(conn, email)
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: AsyncConnection = Depends(get_conn),
) -> Optional[UserPublic]:
    if not creds:
        return None
    try:
        payload = decode_token(creds.credentials)
        email = payload.get("sub")
        if not email:
            return None
        user = await _load_user_by_email(conn, email)
        return user
    except HTTPException:
        return None
