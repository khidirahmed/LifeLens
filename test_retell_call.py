#!/usr/bin/env python3
"""
Test Retell outbound call using lifelens_retell (same as relay_server on fall).

Usage from repo root:
  pip install requests python-dotenv
  python3 test_retell_call.py
  python3 test_retell_call.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from lifelens_retell import build_retell_call_payload, send_retell_fall_call


def mask(s: str, keep: int = 4) -> str:
    if len(s) <= keep:
        return "(short)"
    return s[:keep] + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Retell v2/create-phone-call from .env")
    parser.add_argument("--dry-run", action="store_true", help="Print config and payload only")
    args = parser.parse_args()

    key = os.environ.get("RETELL_API_KEY", "").strip()
    from_num = os.environ.get("RETELL_FROM_NUMBER", "").strip()
    to_num = os.environ.get("RETELL_TO_NUMBER", "").strip() or "(default in lifelens_retell)"
    agent_id = os.environ.get("RETELL_AGENT_ID", "").strip()
    disabled = os.environ.get("RETELL_DISABLE", "").lower() in ("1", "true", "yes")

    print("\n── Config (after lifelens_retell import) ──")
    print(f"  RETELL_API_KEY:     {'OK ' + mask(key) if key else 'MISSING'}")
    print(f"  RETELL_FROM_NUMBER: {from_num or 'MISSING'}")
    print(f"  RETELL_TO_NUMBER:   {to_num}")
    print(f"  RETELL_AGENT_ID:    {agent_id or '—'}")
    print(f"  RETELL_DISABLE:     {disabled!r} {'← blocks real sends' if disabled else ''}")

    sample_msg = (
        "LifeLens test — if you receive this call, Retell outbound voice works.\n"
        "Simulated alert line."
    )
    payload = build_retell_call_payload(sample_msg, clip_name="test_clip.mp4")

    print("\n── Request payload (v2/create-phone-call) ──")
    print(json.dumps({**payload, "_note": "Authorization: Bearer … not shown"}, indent=2))

    if args.dry_run:
        print("\n--dry-run: no HTTP request.")
        return 0

    if not key or not from_num:
        print("\nFix missing vars, then re-run.", file=sys.stderr)
        return 1
    if disabled:
        print(
            "\nRETELL_DISABLE is on — unset for a real test call, or use --dry-run.",
            file=sys.stderr,
        )
        return 1

    send_retell_fall_call(sample_msg, clip_name="test_clip.mp4")
    print(
        "\nDone — check logs above for HTTP result. Spoken content follows your Retell voice agent."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
