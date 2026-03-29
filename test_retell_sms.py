#!/usr/bin/env python3
"""
Send a sample Retell outbound SMS using the same .env loading as analyze_video.py:
  LifeLens/.env then LifeLens/stream_server/.env (later wins).

Usage (run from repo root — LifeLens/, not stream_server/):
  pip install requests python-dotenv
  cd /path/to/LifeLens && python3 test_retell_sms.py
  python3 test_retell_sms.py --dry-run    # only print what would be sent

Why production \"does nothing\": send_retell_fall_sms returns early without logging if
RETELL_API_KEY or RETELL_FROM_NUMBER is missing, or if RETELL_DISABLE is set.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Mirror analyze_video defaults (avoid importing analyze_video → cv2/numpy).
_RETELL_DEFAULT_TO = "+19145319583"


def load_env(repo_root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("Install: pip install python-dotenv", file=sys.stderr)
        sys.exit(1)
    for rel in (".env", "stream_server/.env"):
        p = repo_root / rel
        if p.is_file():
            load_dotenv(p, override=True)
            print(f"Loaded {p}")


def mask(s: str, keep: int = 4) -> str:
    if len(s) <= keep:
        return "(short)"
    return s[:keep] + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Retell create-sms-chat from .env")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config and payload only; do not call the API",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    load_env(repo_root)

    key = os.environ.get("RETELL_API_KEY", "").strip()
    from_num = os.environ.get("RETELL_FROM_NUMBER", "").strip()
    to_num = os.environ.get("RETELL_TO_NUMBER", "").strip() or _RETELL_DEFAULT_TO
    agent_id = os.environ.get("RETELL_AGENT_ID", "").strip()
    disabled = os.environ.get("RETELL_DISABLE", "").lower() in ("1", "true", "yes")

    print("\n── Config (after load) ──")
    print(f"  RETELL_API_KEY:     {'OK ' + mask(key) if key else 'MISSING — add to stream_server/.env'}")
    print(f"  RETELL_FROM_NUMBER: {from_num or 'MISSING — SMS-capable Retell number (E.164)'}")
    print(f"  RETELL_TO_NUMBER:   {to_num}")
    print(f"  RETELL_AGENT_ID:    {agent_id or '— (uses number-bound agent)'}")
    print(f"  RETELL_DISABLE:     {disabled!r} {'← blocks real analyze_video sends' if disabled else ''}")

    if not key or not from_num:
        print("\nFix missing vars, then re-run.", file=sys.stderr)
        return 1
    if disabled and not args.dry_run:
        print(
            "\nRETELL_DISABLE is on — analyze_video will not send. "
            "Unset it for real sends, or use --dry-run to inspect payload.",
            file=sys.stderr,
        )
        return 1

    sample_msg = (
        "LifeLens test at sample time—if you see this SMS, Retell outbound SMS works.\n"
        "alert @ 0.0 mag=0.00 (simulated fall line)"
    )
    sms_text = (
        "LifeLens: possible fall detected\n"
        f"{sample_msg}\n"
        "Clip: test_clip.mp4"
    )[:2000]

    payload: dict = {
        "from_number": from_num,
        "to_number": to_num,
        "metadata": {"source": "lifelens_test_retell_sms", "clip": "test_clip.mp4"},
        "retell_llm_dynamic_variables": {
            "sms_text": sms_text,
            "alert_message": sample_msg[:2000],
            "clip_name": "test_clip.mp4",
        },
    }
    if agent_id:
        payload["override_agent_id"] = agent_id

    print("\n── Request payload (create-sms-chat) ──")
    print(json.dumps({**payload, "_note": "Authorization header not shown"}, indent=2))

    if args.dry_run:
        print("\n--dry-run: no HTTP request.")
        return 0

    try:
        import requests
    except ImportError:
        print("Install: pip install requests", file=sys.stderr)
        return 1

    r = requests.post(
        "https://api.retellai.com/create-sms-chat",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    print(f"\n── Response HTTP {r.status_code} ──")
    body: dict | str
    try:
        body = r.json()
        print(json.dumps(body, indent=2))
    except Exception:
        body = r.text[:2000]
        print(body)

    if r.status_code != 200:
        msg = ""
        if isinstance(body, dict):
            msg = str(body.get("message", ""))
        if "a2p-application" in msg.lower() or "a2p" in msg.lower():
            print(
                "\nRetell says this From number has no SMS / A2P registration.\n"
                "  • In Retell: finish SMS setup for US numbers (brand + campaign / 10DLC), or use a\n"
                "    number Retell lists as SMS-capable with A2P approved.\n"
                "  • Voice-only or pending-registration numbers return this 404.\n"
                "  • Set RETELL_FROM_NUMBER to the exact E.164 shown in Retell → Phone numbers.\n"
                "  Docs: https://docs.retellai.com/deploy/enable-sms",
                file=sys.stderr,
            )
        else:
            print(
                "\nOther common causes: wrong API key; to_number not E.164; chat agent not\n"
                "bound to the number / bad RETELL_AGENT_ID; billing.",
                file=sys.stderr,
            )
        return 1

    print("\nOK — Retell accepted the request. First SMS text still comes from your agent "
          "(use {{sms_text}} in the opening SMS / prompt).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
