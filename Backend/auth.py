"""
Auth utilities: password hashing, JWT creation & verification.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, Header, HTTPException
from database import get_db

SECRET_KEY  = os.getenv("JWT_SECRET_KEY", "change-this-in-production-please")
ALGORITHM   = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_MINS = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(user_id: str, username: str) -> str:
    expire  = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINS)
    payload = {"sub": user_id, "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(authorization: str = Header(None)) -> dict:
    """
    Dependency injected into protected routes.
    Decodes the JWT and returns the user document from MongoDB.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token   = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    user_id = payload.get("sub")

    db   = get_db()
    from bson import ObjectId
    user = await db["users"].find_one({"_id": ObjectId(user_id)})

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
