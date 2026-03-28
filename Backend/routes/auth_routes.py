"""
Auth routes: /auth/register, /auth/login, /auth/me
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from auth import create_token, hash_password, verify_password, get_current_user
from database import get_db
from models import AuthResponse, LoginRequest, RegisterRequest, UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(req: RegisterRequest):
    """
    Create a new user account.
    Stores hashed password in MongoDB — plain text is never saved.
    """
    db = get_db()

    # Check for duplicates
    if await db["users"].find_one({"username": req.username}):
        raise HTTPException(status_code=409, detail="Username already taken")
    if await db["users"].find_one({"email": req.email}):
        raise HTTPException(status_code=409, detail="Email already registered")

    doc = {
        "username":      req.username,
        "email":         req.email,
        "password_hash": hash_password(req.password),
        "full_name":     req.full_name,
        "role":          "user",
        "created_at":    datetime.now(timezone.utc),
    }
    result  = await db["users"].insert_one(doc)
    user_id = str(result.inserted_id)
    token   = create_token(user_id, req.username)

    return AuthResponse(
        token=token,
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        message="Account created successfully",
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """
    Verify credentials and return a JWT token.
    """
    db   = get_db()
    user = await db["users"].find_one({"username": req.username})

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(str(user["_id"]), user["username"])

    return AuthResponse(
        token=token,
        username=user["username"],
        email=user["email"],
        full_name=user.get("full_name"),
        message="Login successful",
    )


@router.get("/me", response_model=UserProfile)
async def me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserProfile(
        username=current_user["username"],
        email=current_user["email"],
        full_name=current_user.get("full_name"),
        created_at=current_user["created_at"],
    )
