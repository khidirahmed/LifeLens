"""
Retell outbound voice call for LifeLens fall alerts.

Loaded by relay_server.py when a fall result arrives over LIFELENS_RECEIVER_WS.
( analyze_video.py does not place calls — only HTTP/Telegram clip alerts there. )

Env: LifeLens/.env then LifeLens/stream_server/.env (later wins), same as analyze_video.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_RETELL_DEFAULT_TO = "+19145319583"
_env_loaded = False

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None  # type: ignore[misc, assignment]


def _maybe_load_env() -> None:
    global _env_loaded
    if _env_loaded:
        return
    if _load_dotenv is not None:
        root = Path(__file__).resolve().parent
        for p in (root / ".env", root / "stream_server" / ".env"):
            if p.is_file():
                _load_dotenv(p, override=True)
    _env_loaded = True


_maybe_load_env()


def _env_str(key: str, default: str = "") -> str:
    _maybe_load_env()
    v = os.environ.get(key)
    return default if v is None else str(v).strip()


def events_to_alert_message(events: list[dict[str, Any]]) -> str:
    """Format VLM/receiver event list for Retell dynamic variables."""
    lines: list[str] = []
    for e in events:
        lines.append(
            f"{e.get('type', 'alert')} @ {e.get('timestamp', '?')} "
            f"mag={float(e.get('magnitude', 0) or 0):.2f} {e.get('brief', '')}"
        )
    return "\n".join(lines) if lines else "LifeLens alert"


def build_retell_call_payload(message: str, *, clip_name: str = "") -> dict[str, Any]:
    """JSON body for POST /v2/create-phone-call (for tests / dry-run)."""
    _maybe_load_env()
    lines = ["LifeLens: possible fall detected", message]
    if clip_name:
        lines.append(f"Clip: {clip_name}")
    call_summary = "\n".join(lines)[:2000]
    to_num = _env_str("RETELL_TO_NUMBER", _RETELL_DEFAULT_TO).strip() or _RETELL_DEFAULT_TO
    payload: dict[str, Any] = {
        "from_number": _env_str("RETELL_FROM_NUMBER", "").strip(),
        "to_number": to_num,
        "metadata": {
            "source": "lifelens",
            "clip": clip_name[:240],
        },
        "retell_llm_dynamic_variables": {
            "call_summary": call_summary,
            "alert_message": message[:2000],
            "clip_name": clip_name[:200],
        },
    }
    agent_id = _env_str("RETELL_AGENT_ID", "").strip()
    if agent_id:
        payload["override_agent_id"] = agent_id
    return payload


def send_retell_fall_call(message: str, *, clip_name: str = "") -> None:
    """
    Start Retell outbound call to RETELL_TO_NUMBER.

    https://docs.retellai.com/api-references/create-phone-call
    """
    _maybe_load_env()
    key = _env_str("RETELL_API_KEY", "").strip()
    from_num = _env_str("RETELL_FROM_NUMBER", "").strip()
    if not key or not from_num:
        logger.warning(
            "Retell call skipped: need RETELL_API_KEY and RETELL_FROM_NUMBER "
            "(run python3 test_retell_call.py from repo root)"
        )
        return
    if _env_str("RETELL_DISABLE", "").lower() in ("1", "true", "yes"):
        logger.warning("Retell call skipped: RETELL_DISABLE is set")
        return
    payload = build_retell_call_payload(message, clip_name=clip_name)
    if not payload.get("from_number"):
        logger.warning("Retell call skipped: RETELL_FROM_NUMBER empty after load")
        return
    to_num = str(payload.get("to_number", ""))
    try:
        import requests

        r = requests.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if r.status_code not in (200, 201):
            err = r.text[:800]
            logger.error("Retell create-phone-call failed: %s %s", r.status_code, err)
            try:
                detail = r.json()
                api_msg = str(detail.get("message", "")).lower()
            except Exception:
                api_msg = err.lower()
            if "outbound agent" in api_msg or "agent id" in api_msg:
                logger.error(
                    "Retell: assign an outbound VOICE agent to this From number in the Retell "
                    "dashboard (Phone numbers → your number), or set RETELL_AGENT_ID in .env to a "
                    "voice agent id (override_agent_id)."
                )
        else:
            logger.info("Retell outbound call started -> %s", to_num)
    except ImportError:
        logger.warning("Retell skipped: pip install requests")
    except Exception as e:
        logger.error("Retell error: %s", e)
