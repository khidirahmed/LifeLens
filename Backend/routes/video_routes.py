"""
Video routes: /upload/video, /videos (list)
"""

import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import get_current_user
from database import get_db
from models import UploadResponse, VideoRecord

router = APIRouter(tags=["videos"])

HEX_API_KEY  = os.getenv("HEX_API_KEY",  "your-hex-api-key")
HEX_BASE_URL = os.getenv("HEX_BASE_URL", "https://api.hex.tech")
HEX_BUCKET   = os.getenv("HEX_BUCKET",   "lifelens-videos")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload/video", response_model=UploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Receive a video from the iOS app:
      1. Validate MIME type
      2. Save locally as backup
      3. Upload to Hex storage
      4. Run safety analysis (LLM stub)
      5. Store metadata in MongoDB
      6. Return verdict + storage URL
    """
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")

    video_id  = str(uuid.uuid4())
    user_id   = str(current_user["_id"])
    username  = current_user["username"]
    safe_name = f"{video_id}_{file.filename or 'video.mov'}"
    timestamp = datetime.now(timezone.utc)

    video_bytes = await file.read()
    size_mb     = len(video_bytes) / (1024 * 1024)
    print(f"[{timestamp.isoformat()}] 📥 {file.filename}  {size_mb:.2f} MB  user={username}")

    # Save locally
    local_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(local_path, "wb") as f:
        f.write(video_bytes)

    # Upload to Hex
    storage_url = await upload_to_hex(video_bytes, safe_name, file.content_type or "video/quicktime")
    print(f"  Hex URL → {storage_url}")

    # Safety analysis placeholder
    analysis = await analyze_video(local_path)

    # Persist to MongoDB
    db  = get_db()
    doc = {
        "video_id":    video_id,
        "user_id":     user_id,
        "filename":    file.filename or safe_name,
        "storage_url": storage_url,
        "safe":        analysis["safe"],
        "message":     analysis["message"],
        "file_size_mb": round(size_mb, 2),
        "uploaded_at": timestamp,
    }
    await db["videos"].insert_one(doc)

    return UploadResponse(
        video_id=video_id,
        storage_url=storage_url,
        safe=analysis["safe"],
        message=analysis["message"],
    )


@router.get("/videos")
async def list_videos(current_user: dict = Depends(get_current_user)):
    """Return all videos uploaded by the current user."""
    db      = get_db()
    user_id = str(current_user["_id"])
    cursor  = db["videos"].find({"user_id": user_id}).sort("uploaded_at", -1)
    videos  = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        videos.append(doc)
    return {"videos": videos, "count": len(videos)}


# ── Hex helper ────────────────────────────────────────────────────────────────

async def upload_to_hex(data: bytes, filename: str, content_type: str) -> str:
    """
    Upload video bytes to Hex cloud storage.
    TODO: confirm exact endpoint + auth headers from your Hex account.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{HEX_BASE_URL}/v1/storage/{HEX_BUCKET}/upload",
                headers={
                    "Authorization": f"Bearer {HEX_API_KEY}",
                    "X-Filename": filename,
                    "Content-Type": content_type,
                },
                content=data,
            )
            if response.status_code in (200, 201):
                body = response.json()
                return body.get("url") or body.get("storage_url") or f"hex://{HEX_BUCKET}/{filename}"
            print(f"  ⚠️  Hex {response.status_code}: {response.text}")
    except Exception as exc:
        print(f"  ⚠️  Hex upload error: {exc}")

    return f"local://uploads/{filename}"


# ── LLM stub ─────────────────────────────────────────────────────────────────

async def analyze_video(video_path: str) -> dict:
    """
    Placeholder — will be replaced with a vision-LLM call (e.g. LLaVA via Ollama).
    Samples frames every N seconds → sends to model → returns safe/unsafe verdict.
    """
    return {
        "safe":    True,
        "message": "Video stored successfully. LLM analysis coming soon.",
    }
