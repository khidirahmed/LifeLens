import os
import uuid
import requests
from pathlib import Path

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database import db
from models import User, Alert

alert_bp = Blueprint("alert", __name__)

RETELL_BASE = "https://api.retellai.com"
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['RETELL_API_KEY']}",
        "Content-Type": "application/json",
    }


def _place_call(to_number: str, video_path: str | None = None) -> dict:
    payload = {
        "from_number": os.environ["RETELL_FROM_NUMBER"],
        "to_number": to_number,
        "override_agent_id": os.environ["RETELL_AGENT_ID"],
        "metadata": {"video_clip": video_path or "none"},
    }
    resp = requests.post(
        f"{RETELL_BASE}/v2/create-phone-call",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


@alert_bp.route("/alert", methods=["POST"])
def alert():
    """Called by the GX10 when an emergency is detected. No auth — internal endpoint."""
    users = User.query.all()
    if not users:
        return jsonify({"error": "No registered users to alert"}), 400

    # Save video clip if provided
    video_path = None
    video_file = request.files.get("video")
    if video_file and video_file.filename:
        ext = Path(video_file.filename).suffix or ".mp4"
        video_path = str(UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}")
        video_file.save(video_path)

    results = []
    for user in users:
        try:
            retell_resp = _place_call(user.phone_number, video_path)
            db.session.add(Alert(
                user_id=user.id,
                call_id=retell_resp.get("call_id"),
                video_path=video_path,
                status="triggered",
            ))
            results.append({"user": user.email, "call_id": retell_resp.get("call_id"), "status": "ok"})
        except Exception as exc:
            results.append({"user": user.email, "error": str(exc)})

    db.session.commit()
    return jsonify({"message": "Alert processed", "results": results}), 200


@alert_bp.route("/register-contact", methods=["POST"])
@jwt_required()
def register_contact():
    """Update the logged-in user's emergency contact phone number."""
    user = User.query.get_or_404(int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    phone = data.get("phone_number", "").strip()

    if not phone.startswith("+"):
        return jsonify({"error": "phone_number must be E.164 format"}), 400

    user.phone_number = phone
    db.session.commit()
    return jsonify({"message": "Contact updated", "phone_number": phone}), 200
