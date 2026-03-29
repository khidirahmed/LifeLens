"""
LifeLens Backend — FastAPI + Supabase Auth
==========================================
Environment variables required (all from Supabase Dashboard → Project Settings → API):
  SUPABASE_URL          — your project URL  (https://xxxx.supabase.co)
  SUPABASE_SECRET_KEY   — service role key  (bypasses RLS, server-side only)
  SUPABASE_PUBLISH_KEY  — anon/publishable key (used for sign-in)

No JWT_SECRET needed — Supabase Auth manages all tokens.

Endpoints:
  POST /auth/register   — create account (role: caregiver | resident)
  POST /auth/login      — returns Supabase access_token + user profile
  GET  /alerts          — list non-dismissed alerts for current user (last 24 h)
  POST /alerts          — create alert (called by relay/analysis pipeline)
  DELETE /alerts/{id}   — dismiss an alert
  GET  /health          — health check

Run:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from supabase import Client, create_client

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Config — only 3 env vars needed
# ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()   # service role
SUPABASE_PUBLISH_KEY = os.getenv("SUPABASE_PUBLISH_KEY", "").strip()  # anon / public

ALERT_TTL_H = 24

# ──────────────────────────────────────────────────────────────
# Two Supabase clients
#   sb_admin  — service role key, bypasses RLS, used for DB queries & admin auth ops
#   sb_anon   — publishable key, used for sign_in_with_password (returns user JWT)
# ──────────────────────────────────────────────────────────────
sb_admin: Client | None = None
sb_anon: Client | None = None


def _admin() -> Client:
    if sb_admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not ready — check startup logs.",
        )
    return sb_admin


def _anon() -> Client:
    if sb_anon is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not ready — check startup logs.",
        )
    return sb_anon


# ──────────────────────────────────────────────────────────────
# Lifespan — validate config & test connectivity on startup
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: RUF029
    global sb_admin, sb_anon

    missing = [
        name for name, val in [
            ("SUPABASE_URL", SUPABASE_URL),
            ("SUPABASE_SECRET_KEY", SUPABASE_SECRET_KEY),
            ("SUPABASE_PUBLISH_KEY", SUPABASE_PUBLISH_KEY),
        ]
        if not val
    ]
    if missing:
        msg = f"Missing env vars: {', '.join(missing)}\nFind them at: Supabase Dashboard → Project Settings → API"
        log.error(msg)
        raise RuntimeError(msg)

    try:
        sb_admin = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        sb_anon = create_client(SUPABASE_URL, SUPABASE_PUBLISH_KEY)
        # Connectivity smoke-test
        sb_admin.table("users").select("id").limit(1).execute()
        log.info("Supabase connected ✓  (admin + anon clients ready)")
    except Exception as exc:
        log.error("Supabase startup failed: %s", exc)
        raise RuntimeError(f"Cannot connect to Supabase: {exc}") from exc

    yield  # ← app is live here

    sb_admin = None
    sb_anon = None
    log.info("Supabase clients released.")


# ──────────────────────────────────────────────────────────────
# App & Middleware
# ──────────────────────────────────────────────────────────────
app = FastAPI(title="LifeLens API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer = HTTPBearer()


# ──────────────────────────────────────────────────────────────
# Auth helper — verify Supabase JWT and return public.users row
# ──────────────────────────────────────────────────────────────
def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    token = creds.credentials
    admin = _admin()

    # Verify the token with Supabase Auth — raises if expired / invalid
    try:
        user_resp = admin.auth.get_user(token)
        user_id = str(user_resp.user.id)
    except Exception as exc:
        log.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Fetch the matching profile row
    try:
        rows = admin.table("users").select("*").eq("id", user_id).execute().data
    except Exception as exc:
        log.error("DB error fetching user profile: %s", exc)
        raise HTTPException(status_code=503, detail="Database error")

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile not found",
        )
    return rows[0]


# ──────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    role: str = Field(..., pattern="^(caregiver|resident)$")


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    token: str
    refresh_token: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    message: str


class AlertCreate(BaseModel):
    """Payload sent by the relay/analysis pipeline when a fall is detected."""
    resident_username: str
    message: str
    severity: str = "high"
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    timestamp: Optional[datetime] = None


class AlertResponse(BaseModel):
    id: str
    message: str
    severity: str
    video_url: Optional[str]
    thumbnail_url: Optional[str]
    timestamp: datetime
    created_at: datetime
    dismissed: bool


# ──────────────────────────────────────────────────────────────
# Auth routes
# ──────────────────────────────────────────────────────────────
@app.post("/auth/register", status_code=201, response_model=UserResponse)
async def register(req: RegisterRequest):
    admin = _admin()
    anon = _anon()

    # 1. Check username is not already taken in public.users
    try:
        taken = admin.table("users").select("id").eq("username", req.username).execute().data
        if taken:
            raise HTTPException(status_code=409, detail="Username already taken")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("DB error checking username: %s", exc)
        raise HTTPException(status_code=503, detail="Database error")

    # 2. Create the Supabase Auth user (admin API — auto-confirms email, no email sent)
    try:
        auth_resp = admin.auth.admin.create_user({
            "email": str(req.email),
            "password": req.password,
            "email_confirm": True,   # skip confirmation email for backend-managed accounts
        })
        user_id = str(auth_resp.user.id)
    except Exception as exc:
        err_str = str(exc).lower()
        if "already" in err_str or "exists" in err_str or "registered" in err_str:
            raise HTTPException(status_code=409, detail="Email already registered")
        log.error("Supabase Auth create_user failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create auth account")

    # 3. Insert profile row in public.users (linked to auth.users.id)
    try:
        admin.table("users").insert({
            "id": user_id,
            "username": req.username,
            "email": str(req.email),
            "full_name": req.full_name,
            "role": req.role,
        }).execute()
    except Exception as exc:
        # Roll back: delete the auth user we just created so there's no orphan
        try:
            admin.auth.admin.delete_user(user_id)
        except Exception:
            pass
        log.error("DB error inserting user profile (rolled back auth user): %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save user profile")

    # 4. Sign in immediately to return a token
    try:
        session = anon.auth.sign_in_with_password({
            "email": str(req.email),
            "password": req.password,
        }).session
    except Exception as exc:
        log.error("Sign-in after register failed: %s", exc)
        raise HTTPException(status_code=500, detail="Account created but sign-in failed — try logging in")

    log.info("Registered user %s (%s)", req.username, user_id)
    return UserResponse(
        token=session.access_token,
        refresh_token=session.refresh_token,
        username=req.username,
        email=str(req.email),
        full_name=req.full_name,
        role=req.role,
        message="Account created successfully",
    )


@app.post("/auth/login", response_model=UserResponse)
async def login(req: LoginRequest):
    admin = _admin()
    anon = _anon()

    # 1. Look up the email associated with the username
    try:
        rows = admin.table("users").select("email, role, full_name").eq("username", req.username).execute().data
    except Exception as exc:
        log.error("DB error during login lookup: %s", exc)
        raise HTTPException(status_code=503, detail="Database error")

    if not rows:
        # Generic message — don't reveal whether username exists
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    profile = rows[0]

    # 2. Sign in via Supabase Auth (uses email + password)
    try:
        result = anon.auth.sign_in_with_password({
            "email": profile["email"],
            "password": req.password,
        })
        session = result.session
    except Exception:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    log.info("Login: %s", req.username)
    return UserResponse(
        token=session.access_token,
        refresh_token=session.refresh_token,
        username=req.username,
        email=profile["email"],
        full_name=profile.get("full_name"),
        role=profile["role"],
        message="Login successful",
    )


# ──────────────────────────────────────────────────────────────
# Alerts routes
# ──────────────────────────────────────────────────────────────
@app.get("/alerts", response_model=list[AlertResponse])
async def get_alerts(
    current_user: dict = Depends(get_current_user),
    resident_username: Optional[str] = None,
):
    """
    Residents/cregivers can both request alerts for a specific `resident_username`.

    If `resident_username` is not provided, alerts for `current_user.username` are returned.
    """
    admin = _admin()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ALERT_TTL_H)).isoformat()
    target = (resident_username or "").strip() or current_user["username"]

    try:
        result = (
            admin.table("alerts")
            .select("id, message, severity, video_url, thumbnail_url, event_at, created_at, dismissed")
            .eq("resident_username", target)
            .eq("dismissed", False)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        log.error("DB error fetching alerts: %s", exc)
        raise HTTPException(status_code=503, detail="Database error")

    return [
        AlertResponse(
            id=str(d["id"]),
            message=d["message"],
            severity=d.get("severity", "high"),
            video_url=d.get("video_url"),
            thumbnail_url=d.get("thumbnail_url"),
            timestamp=d.get("event_at") or d["created_at"],
            created_at=d["created_at"],
            dismissed=d.get("dismissed", False),
        )
        for d in (result.data or [])
    ]


@app.post("/alerts", status_code=201)
async def create_alert(req: AlertCreate):
    """
    Called by the relay/analysis pipeline — no user auth required.
    In production, add a shared pipeline secret header check here.
    """
    admin = _admin()
    now = datetime.now(timezone.utc)
    event_at = req.timestamp or now

    try:
        result = admin.table("alerts").insert({
            "resident_username": req.resident_username,
            "message": req.message,
            "severity": req.severity,
            "video_url": req.video_url,
            "thumbnail_url": req.thumbnail_url,
            "event_at": event_at.isoformat(),
            "created_at": now.isoformat(),
            "dismissed": False,
        }).execute()
    except Exception as exc:
        log.error("DB error creating alert: %s", exc)
        raise HTTPException(status_code=503, detail="Database error — could not create alert")

    if not result.data:
        raise HTTPException(status_code=500, detail="Alert insert returned no data")

    alert_id = str(result.data[0]["id"])
    log.info("Alert created: %s for resident '%s'", alert_id, req.resident_username)
    return {"id": alert_id, "message": "Alert created"}


@app.delete("/alerts/{alert_id}", status_code=204)
async def dismiss_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    resident_username: Optional[str] = None,
):
    # Validate UUID format
    try:
        UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alert not found")

    admin = _admin()
    target = (resident_username or "").strip() or current_user["username"]

    # Confirm alert exists and belongs to this resident before updating
    try:
        owned = (
            admin.table("alerts")
            .select("id")
            .eq("id", alert_id)
            .eq("resident_username", target)
            .eq("dismissed", False)
            .execute()
            .data
        )
    except Exception as exc:
        log.error("DB error checking alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=503, detail="Database error")

    if not owned:
        raise HTTPException(status_code=404, detail="Alert not found")

    try:
        admin.table("alerts").update({"dismissed": True}).eq("id", alert_id).execute()
    except Exception as exc:
        log.error("DB error dismissing alert %s: %s", alert_id, exc)
        raise HTTPException(status_code=503, detail="Database error")


# ──────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    db_status = "not_initialised"
    if sb_admin is not None:
        try:
            sb_admin.table("users").select("id").limit(1).execute()
            db_status = "connected"
        except Exception as exc:
            log.warning("Health check DB error: %s", exc)
            db_status = "error"
    return {"status": "ok", "database": db_status, "version": app.version}
