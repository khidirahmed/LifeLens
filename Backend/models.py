"""
Pydantic models for request/response validation and MongoDB documents.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username:  str = Field(..., min_length=3, max_length=30)
    email:     EmailStr
    password:  str = Field(..., min_length=6)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token:     str
    username:  str
    email:     str
    full_name: Optional[str]
    message:   str


class UserProfile(BaseModel):
    username:   str
    email:      str
    full_name:  Optional[str]
    created_at: datetime


# ── Videos ────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    video_id:    str
    storage_url: str
    safe:        bool
    message:     str


class VideoRecord(BaseModel):
    """Shape of a document stored in the 'videos' collection."""
    video_id:    str
    user_id:     str
    filename:    str
    storage_url: str
    safe:        bool
    message:     str
    file_size_mb: float
    uploaded_at: datetime
