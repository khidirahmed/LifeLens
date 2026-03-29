"""RetellAI outbound call logic — isolated from Flask routes."""

import os
import requests

RETELL_BASE_URL = "https://api.retellai.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['RETELL_API_KEY']}",
        "Content-Type": "application/json",
    }


def trigger_emergency_call(to_number: str, senior_name: str, video_path: str | None = None) -> dict:
    """
    Place an outbound call to `to_number` notifying them of an emergency.

    Args:
        to_number:   E.164 phone number of the emergency contact.
        senior_name: Name of the senior — injected into the agent prompt.
        video_path:  Local path to a saved video clip (logged/stored; not streamed over the call).

    Returns:
        The JSON response body from RetellAI (contains call_id, call_status, etc.)
    """
    payload = {
        "from_number": os.environ["RETELL_FROM_NUMBER"],
        "to_number": to_number,
        "override_agent_id": os.environ["RETELL_AGENT_ID"],
        "retell_llm_dynamic_variables": {
            "senior_name": senior_name,
        },
        "metadata": {
            "video_clip": video_path or "none",
        },
    }

    response = requests.post(
        f"{RETELL_BASE_URL}/v2/create-phone-call",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
