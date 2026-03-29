"""
LifeLens video analysis — Qwen2-VL fall screening via an OpenAI-compatible HTTP API.

Samples video frames, sends batched image+text requests to LIFELENS_VLM_BASE_URL,
parses JSON. Requires LIFELENS_VLM_API_KEY and LIFELENS_VLM_BASE_URL.

Optional: LIFELENS_ALERT_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID for clip alerts.
Optional SMS on fall: Retell to RETELL_TO_NUMBER — RETELL_* in .env.example.
load_dotenv(stream_server/.env) when python-dotenv is installed.

Library API for segment_receiver.py:
  analyze_clip(mp4_bytes: bytes) -> list[dict]
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".MP4", ".MOV", ".AVI"}

# Retell outbound SMS recipient (E.164). Override with RETELL_TO_NUMBER in .env if needed.
_RETELL_DEFAULT_TO = "+19145319583"

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]


def _maybe_load_env() -> None:
    if load_dotenv is None:
        return
    here = Path(__file__).resolve().parent
    # Load both (if present); later files override so stream_server/.env wins over parent .env.
    for p in (here / ".env", here / "stream_server" / ".env"):
        if p.is_file():
            load_dotenv(p, override=True)


_maybe_load_env()


def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key, "").strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _strip_inline_comment(v: str) -> str:
    if "#" in v:
        v = v.split("#", 1)[0].strip()
    return v


def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key, "").strip()
    if not v:
        return default
    v = _strip_inline_comment(v)
    try:
        return int(v)
    except ValueError:
        return default


def _env_str(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return default if v is None else str(v).strip()


@dataclass
class Config:
    input_folder: str = "/home/asus/LifeLens/video/input"
    output_folder: str = "/home/asus/LifeLens/video/output"

    # VLM (overridden by env on use)
    vlm_api_key: str = ""
    vlm_base_url: str = ""
    vlm_model: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    # Higher sample rate + more frames + motion-aware subsampling → fewer missed falls.
    vlm_sample_fps: float = 3.0
    vlm_max_frames: int = 48
    # If the backend limits images per request (e.g. 4), set this lower in .env.
    vlm_max_images_per_request: int = 8
    # Re-use tail frames in the next request so a fall on a batch boundary is still seen twice.
    vlm_batch_overlap: int = 2
    vlm_max_side: int = 768
    vlm_jpeg_quality: int = 82
    vlm_timeout_sec: float = 120.0
    vlm_max_tokens: int = 1024


def _config_from_env() -> Config:
    return Config(
        input_folder=_env_str("LIFELENS_VIDEO_INPUT", Config.input_folder),
        output_folder=_env_str("LIFELENS_VIDEO_OUTPUT", Config.output_folder),
        vlm_api_key=_env_str("LIFELENS_VLM_API_KEY", ""),
        vlm_base_url=_env_str("LIFELENS_VLM_BASE_URL", ""),
        vlm_model=_env_str("LIFELENS_VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
        vlm_sample_fps=_env_float("LIFELENS_VLM_SAMPLE_FPS", 3.0),
        vlm_max_frames=_env_int("LIFELENS_VLM_MAX_FRAMES", 48),
        vlm_max_images_per_request=_env_int("LIFELENS_VLM_MAX_IMAGES_PER_REQUEST", 8),
        vlm_batch_overlap=_env_int("LIFELENS_VLM_BATCH_OVERLAP", 2),
        vlm_max_side=_env_int("LIFELENS_VLM_MAX_SIDE", 768),
        vlm_jpeg_quality=_env_int("LIFELENS_VLM_JPEG_QUALITY", 82),
        vlm_timeout_sec=_env_float("LIFELENS_VLM_TIMEOUT_SEC", 120.0),
        vlm_max_tokens=_env_int("LIFELENS_VLM_MAX_TOKENS", 1024),
    )


cfg = _config_from_env()


def _resize_long_edge(bgr: np.ndarray, max_side: int) -> np.ndarray:
    h, w = bgr.shape[:2]
    long = max(h, w)
    if long <= max_side:
        return bgr
    scale = max_side / float(long)
    nw, nh = int(w * scale), int(h * scale)
    return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def _encode_jpeg(bgr: np.ndarray, quality: int) -> bytes:
    q = max(1, min(100, int(quality)))
    ok, buf = cv2.imencode(
        ".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), q]
    )
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return buf.tobytes()


def _coerce_fall_flag(val: Any) -> bool:
    if val is True:
        return True
    if val is False or val is None:
        return False
    if isinstance(val, str):
        return val.strip().lower() in ("true", "yes", "1")
    if isinstance(val, (int, float)):
        return bool(val)
    return False


def _subsample_with_motion_bias(
    candidate: list[tuple[int, float, bytes]],
    motion: np.ndarray,
    max_frames: int,
) -> list[tuple[int, float, bytes]]:
    """
    Keep timeline spread *and* frames where consecutive-sample motion jumps (typical for falls).
    """
    n = len(candidate)
    if n <= max_frames:
        return candidate

    m = np.asarray(motion, dtype=np.float64)
    time_idx = np.unique(
        np.clip(
            np.round(np.linspace(0, n - 1, max_frames)).astype(int),
            0,
            n - 1,
        )
    )
    sel: set[int] = set(int(i) for i in time_idx)
    sel.update({0, n - 1})
    for idx in np.argsort(m)[::-1]:
        sel.add(int(idx))
        if len(sel) >= max_frames + 20:
            break

    if len(sel) <= max_frames:
        logger.info("Subsampling %d→%d frames (spread + motion union fits cap)", n, len(sel))
        return [candidate[i] for i in sorted(sel)]

    # Trim: always keep first/last index, then highest-motion candidates until max_frames
    keep: set[int] = {0, n - 1}
    for idx in np.argsort(m)[::-1]:
        if len(keep) >= max_frames:
            break
        keep.add(int(idx))
    for idx in time_idx:
        if len(keep) >= max_frames:
            break
        keep.add(int(idx))
    while len(keep) > max_frames:
        inner = sorted(keep - {0, n - 1}, key=lambda i: m[i])
        if not inner:
            break
        keep.discard(inner[0])
    out = sorted(keep)
    logger.info("Subsampling %d→%d frames (motion-prioritized, endpoints kept)", n, len(out))
    return [candidate[i] for i in out]


def sample_video_frames(
    video_path: str,
    *,
    target_fps: float,
    max_frames: int,
    max_side: int,
    jpeg_quality: int,
) -> tuple[list[tuple[int, float, bytes]], float]:
    """
    Full linear scan across the clip at ~`target_fps` stills per second of timeline,
    then subsample to `max_frames` with **motion bias** so sudden movement (typical of
    falls) is less likely to be discarded.

    Returns ([(frame_index, time_sec, jpeg_bytes), ...], source_fps).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if src_fps <= 0:
        src_fps = 30.0

    stride = max(1, int(round(src_fps / max(target_fps, 0.05))))
    candidate: list[tuple[int, float, bytes]] = []
    motion_scores: list[float] = []
    prev_gray: np.ndarray | None = None
    frame_idx = 0

    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if frame_idx % stride == 0:
            t = frame_idx / src_fps
            small = cv2.resize(bgr, (64, 36), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is None:
                diff = 0.0
            else:
                diff = float(np.mean(cv2.absdiff(gray, prev_gray)))
            prev_gray = gray

            bgr = _resize_long_edge(bgr, max_side)
            jpeg = _encode_jpeg(bgr, jpeg_quality)
            candidate.append((frame_idx, float(t), jpeg))
            motion_scores.append(diff)
        frame_idx += 1

    cap.release()

    if not candidate:
        return [], src_fps

    motion = np.array(motion_scores, dtype=np.float32)
    frames_out = _subsample_with_motion_bias(candidate, motion, max_frames)
    return frames_out, src_fps


_JSON_BLOCK = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _parse_vlm_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"fall": False, "events": []}

    def _try_obj(s: str) -> dict[str, Any] | None:
        try:
            o = json.loads(s)
            return o if isinstance(o, dict) else None
        except json.JSONDecodeError:
            return None

    candidates: list[dict[str, Any]] = []
    whole = _try_obj(text)
    if whole is not None and "fall" in whole:
        candidates.append(whole)

    for fm in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE):
        o = _try_obj(fm.group(1))
        if o is not None and "fall" in o:
            candidates.append(o)

    for m in _JSON_BLOCK.finditer(text):
        o = _try_obj(m.group(0))
        if o is not None and "fall" in o:
            candidates.append(o)

    if candidates:
        for c in candidates:
            if _coerce_fall_flag(c.get("fall")):
                return c
        return candidates[-1]

    if whole is not None:
        return whole
    logger.warning("Could not parse VLM response as JSON; first 400 chars: %r", text[:400])
    return {"fall": False, "events": []}


_SYSTEM_PROMPT = (
    "You are a safety reviewer for egocentric (head-mounted) video. "
    "Images are in time order. Your job is to catch REAL FALLS: sudden loss of balance, collapse, trip, "
    "or the person going quickly toward the ground/floor. "
    "If earlier frames show the person more upright than later frames and later show them low/on the floor, "
    "treat that as a fall unless they are clearly sitting or lying down on purpose. "
    "Do NOT flag only blur with no visible person, or slow controlled kneeling. "
    "Answer with ONLY a JSON object, no markdown."
)

_USER_INSTRUCTIONS = """The legend below lists frame_index and time for each image in chronological order.

Return ONLY this JSON shape:
{"fall": false, "confidence": 0.0, "events": []}

If ANY frames suggest an uncontrolled fall, set fall to true (even if only 1–2 frames show impact).
Use confidence 0.5–0.85 when it looks like a fall but video is noisy. Fill events with objects:
{"frame_index": <int>, "time_sec": <float>, "brief": "<short English description>"}

Use numbers from the legend. Prefer fall true when posture drops abruptly; fall false only when activity is clearly normal standing/walking the whole time or calm intentional rest.
"""



def _build_messages(
    frames: list[tuple[int, float, bytes]],
    *,
    batch_header: str = "",
) -> list[dict[str, Any]]:
    legend_lines = [
        f"{i + 1}. frame_index={fi} approx_time_sec={ts:.2f}s"
        for i, (fi, ts, _) in enumerate(frames)
    ]
    legend = "Frames (same order as the images below):\n" + "\n".join(legend_lines)
    intro = _SYSTEM_PROMPT + "\n\n" + _USER_INSTRUCTIONS + "\n\n" + legend
    if batch_header:
        intro = batch_header + "\n\n" + intro

    content: list[dict[str, Any]] = [
        {"type": "text", "text": intro},
    ]
    for _fi, _ts, jpeg in frames:
        b64 = base64.standard_b64encode(jpeg).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    # Single user message avoids some routers counting system+user image slots oddly.
    return [{"role": "user", "content": content}]


def _call_qwen_vl_once(
    client: Any,
    cfg: Config,
    frames: list[tuple[int, float, bytes]],
    *,
    batch_idx: int,
    batch_total: int,
) -> dict[str, Any]:
    header = ""
    if batch_total > 1:
        header = (
            f"Batch {batch_idx + 1} of {batch_total}: same video segment; "
            f"these frames are in chronological order within the full clip."
        )
    messages = _build_messages(frames, batch_header=header)
    resp = client.chat.completions.create(
        model=cfg.vlm_model,
        messages=messages,
        max_tokens=cfg.vlm_max_tokens,
        temperature=0.35,
    )
    text = (resp.choices[0].message.content or "").strip()
    return _parse_vlm_json(text)


def _frame_batch_ranges(n: int, chunk: int, overlap: int) -> list[tuple[int, int]]:
    """Slice [start:end) windows; consecutive windows share `overlap` frames to avoid missing events on boundaries."""
    if n <= 0:
        return []
    chunk = max(1, int(chunk))
    overlap = max(0, min(int(overlap), chunk - 1))
    step = chunk - overlap
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < n:
        end = min(start + chunk, n)
        ranges.append((start, end))
        if end >= n:
            break
        start += step
    return ranges


def _merge_vlm_event_dicts(merged_events: list[Any], raw: list[Any]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for ev in merged_events:
        if isinstance(ev, dict):
            seen.add(
                (
                    int(ev.get("frame_index", -9999)),
                    round(float(ev.get("time_sec", -9999.0)), 2),
                    str(ev.get("brief", ""))[:80],
                )
            )
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        try:
            fi = int(ev.get("frame_index", -9999))
            ts = round(float(ev.get("time_sec", -9999.0)), 2)
        except (TypeError, ValueError):
            fi, ts = -9999, -9999.0
        br = str(ev.get("brief", ""))[:80]
        key = (fi, ts, br)
        if key in seen:
            continue
        seen.add(key)
        merged_events.append(ev)


def _call_qwen_vl(cfg: Config, frames: list[tuple[int, float, bytes]]) -> dict[str, Any]:
    if not cfg.vlm_api_key:
        here = Path(__file__).resolve().parent
        hint = (
            f"LIFELENS_VLM_API_KEY is empty after loading .env — put the key in "
            f"{here / 'stream_server' / '.env'} or {here / '.env'}; "
            f"install python-dotenv (pip install python-dotenv) on the analysis machine."
        )
        raise RuntimeError(hint)
    if not cfg.vlm_base_url:
        raise RuntimeError("LIFELENS_VLM_BASE_URL is not set")

    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("Install the OpenAI-compatible SDK: pip install openai") from e

    chunk = max(1, int(cfg.vlm_max_images_per_request))
    client = OpenAI(
        api_key=cfg.vlm_api_key,
        base_url=cfg.vlm_base_url.rstrip("/"),
        timeout=cfg.vlm_timeout_sec,
    )

    overlaps = max(0, int(cfg.vlm_batch_overlap))
    ranges = _frame_batch_ranges(len(frames), chunk, overlaps)

    if len(ranges) <= 1:
        t0 = time.monotonic()
        batch = frames[ranges[0][0] : ranges[0][1]] if ranges else frames
        out = _call_qwen_vl_once(client, cfg, batch, batch_idx=0, batch_total=1)
        logger.info(
            "VLM request done in %.1fs (%d images, single batch)",
            time.monotonic() - t0,
            len(batch),
        )
        return out

    merged_fall = False
    merged_conf = 0.0
    merged_events: list[Any] = []
    batch_total = len(ranges)
    t0_all = time.monotonic()

    logger.info(
        "VLM batching: %d sampled frames → %d overlapping windows (chunk=%d overlap=%d). "
        "If your API rejects this, set LIFELENS_VLM_MAX_IMAGES_PER_REQUEST lower.",
        len(frames),
        batch_total,
        chunk,
        overlaps,
    )

    for bi, (start, end) in enumerate(ranges):
        batch = frames[start:end]
        t0 = time.monotonic()
        part = _call_qwen_vl_once(client, cfg, batch, batch_idx=bi, batch_total=batch_total)
        elapsed = time.monotonic() - t0
        logger.info(
            "VLM batch %d/%d done in %.1fs (%d images, global frames %d–%d)",
            bi + 1,
            batch_total,
            elapsed,
            len(batch),
            start,
            end - 1,
        )
        if _coerce_fall_flag(part.get("fall")):
            merged_fall = True
            try:
                merged_conf = max(merged_conf, float(part.get("confidence") or 0.0))
            except (TypeError, ValueError):
                pass
            raw = part.get("events") or []
            if isinstance(raw, list):
                _merge_vlm_event_dicts(merged_events, raw)

    logger.info(
        "VLM all batches done in %.1fs (%d images, %d requests)",
        time.monotonic() - t0_all,
        len(frames),
        batch_total,
    )
    return {"fall": merged_fall, "confidence": merged_conf, "events": merged_events}


def vlm_result_to_events(
    data: dict[str, Any],
    *,
    video_name: str,
    source_fps: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not _coerce_fall_flag(data.get("fall")):
        return out

    raw_events = data.get("events") or []
    if not isinstance(raw_events, list):
        raw_events = []

    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        fi = int(ev.get("frame_index", -1))
        tsec = float(ev.get("time_sec", -1.0))
        if fi < 0 and tsec >= 0 and source_fps > 0:
            fi = int(round(tsec * source_fps))
        if tsec < 0 and fi >= 0 and source_fps > 0:
            tsec = fi / source_fps
        mm = int(tsec // 60) if tsec >= 0 else 0
        ss = int(tsec % 60) if tsec >= 0 else 0
        ts = f"{mm:02d}:{ss:02d}"
        out.append(
            {
                "video": video_name,
                "frame": max(0, fi),
                "timestamp": ts,
                "type": "vlm",
                "magnitude": float(data.get("confidence", 0.0) or 0.0),
                "blur": 0.0,
                "brief": str(ev.get("brief", ""))[:500],
            }
        )
    if _coerce_fall_flag(data.get("fall")) and not out:
        out.append(
            {
                "video": video_name,
                "frame": 0,
                "timestamp": "00:00",
                "type": "vlm",
                "magnitude": float(data.get("confidence", 0.0) or 0.0),
                "blur": 0.0,
                "brief": "fall flagged without structured events",
            }
        )
    return out


def post_alert_http(video_path: Path, message: str) -> None:
    url = _env_str("LIFELENS_ALERT_URL", "").strip()
    if not url or not video_path.is_file():
        return
    try:
        import requests

        with open(video_path, "rb") as f:
            r = requests.post(
                url,
                files={"video": (video_path.name, f, "video/mp4")},
                data={"message": message[:2000]},
                timeout=120,
            )
        if r.status_code >= 400:
            logger.error("Alert POST failed: %s %s", r.status_code, r.text[:500])
        else:
            logger.info("Alert POST ok -> %s", url)
    except ImportError:
        logger.warning("Alert skipped: pip install requests")
    except Exception as e:
        logger.error("Alert POST error: %s", e)


def send_telegram_video(video_path: Path, caption: str) -> None:
    token = _env_str("TELEGRAM_BOT_TOKEN", "")
    chat = _env_str("TELEGRAM_CHAT_ID", "")
    if not token or not chat or not video_path.is_file():
        return
    try:
        import requests

        url = f"https://api.telegram.org/bot{token}/sendVideo"
        with open(video_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": chat, "caption": caption[:1024]},
                files={"video": f},
                timeout=120,
            )
        if r.status_code != 200:
            logger.error("Telegram sendVideo failed: %s %s", r.status_code, r.text[:500])
    except ImportError:
        logger.warning("Telegram skipped: pip install requests")
    except Exception as e:
        logger.error("Telegram error: %s", e)


def send_retell_fall_sms(message: str, *, clip_name: str = "") -> None:
    """
    Start a Retell AI outbound SMS to RETELL_TO_NUMBER (E.164) when a fall is detected.

    Requires SMS-capable numbers on Retell. The first SMS is generated by your chat/SMS
    agent; configure the agent to send {{sms_text}} (or {{alert_message}}) as the opening SMS.

    API: https://docs.retellai.com/api-references/create-sms-chat
    """
    key = _env_str("RETELL_API_KEY", "").strip()
    from_num = _env_str("RETELL_FROM_NUMBER", "").strip()
    to_num = _env_str("RETELL_TO_NUMBER", _RETELL_DEFAULT_TO).strip() or _RETELL_DEFAULT_TO
    if not key or not from_num:
        logger.warning(
            "Retell SMS skipped: need RETELL_API_KEY and RETELL_FROM_NUMBER "
            "(run python3 test_retell_sms.py from repo root to verify .env)"
        )
        return
    if _env_str("RETELL_DISABLE", "").lower() in ("1", "true", "yes"):
        logger.warning("Retell SMS skipped: RETELL_DISABLE is set")
        return
    try:
        import requests

        lines = ["LifeLens: possible fall detected", message]
        if clip_name:
            lines.append(f"Clip: {clip_name}")
        sms_text = "\n".join(lines)[:2000]

        payload: dict[str, Any] = {
            "from_number": from_num,
            "to_number": to_num,
            "metadata": {
                "source": "lifelens",
                "clip": clip_name[:240],
            },
            "retell_llm_dynamic_variables": {
                "sms_text": sms_text,
                "alert_message": message[:2000],
                "clip_name": clip_name[:200],
            },
        }
        agent_id = _env_str("RETELL_AGENT_ID", "").strip()
        if agent_id:
            payload["override_agent_id"] = agent_id

        r = requests.post(
            "https://api.retellai.com/create-sms-chat",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if r.status_code != 200:
            err = r.text[:800]
            logger.error("Retell create-sms-chat failed: %s %s", r.status_code, err)
            if "a2p-application" in err.lower():
                logger.error(
                    "Retell: RETELL_FROM_NUMBER needs SMS + A2P/10DLC set up in Retell "
                    "(see docs.retellai.com/deploy/enable-sms)"
                )
        else:
            logger.info("Retell outbound SMS chat started -> %s", to_num)
    except ImportError:
        logger.warning("Retell skipped: pip install requests")
    except Exception as e:
        logger.error("Retell error: %s", e)


def _events_to_alert_message(events: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for e in events:
        lines.append(
            f"{e.get('type', 'alert')} @ {e.get('timestamp', '?')} "
            f"mag={float(e.get('magnitude', 0) or 0):.2f} {e.get('brief', '')}"
        )
    return "\n".join(lines) if lines else "LifeLens alert"


def _notify_fall_clip(video_path: Path, events: list[dict[str, Any]]) -> None:
    if not events or not video_path.is_file():
        return
    msg = _events_to_alert_message(events)
    post_alert_http(video_path, msg)
    send_telegram_video(video_path, msg)
    send_retell_fall_sms(msg, clip_name=video_path.name)


def analyze_video_file(video_path: str, cfg: Config | None = None) -> list[dict[str, Any]]:
    cfg = cfg or _config_from_env()
    path = Path(video_path)
    name = path.name

    frames, src_fps = sample_video_frames(
        str(path),
        target_fps=cfg.vlm_sample_fps,
        max_frames=cfg.vlm_max_frames,
        max_side=cfg.vlm_max_side,
        jpeg_quality=cfg.vlm_jpeg_quality,
    )
    if not frames:
        logger.warning("No frames sampled from %s", name)
        return []

    t0, t1 = frames[0][1], frames[-1][1]
    logger.info(
        "VLM: %s — %d frames @ target_sample_fps=%.2f (source ~%.1f fps); "
        "timeline ~%.2fs–%.2fs (whole clip, then capped at %d for API)",
        name,
        len(frames),
        cfg.vlm_sample_fps,
        src_fps,
        t0,
        t1,
        cfg.vlm_max_frames,
    )
    try:
        raw = _call_qwen_vl(cfg, frames)
    except Exception as e:
        logger.error("VLM call failed: %s", e)
        return []

    events = vlm_result_to_events(raw, video_name=name, source_fps=src_fps)
    if events:
        _notify_fall_clip(path, events)
    elif _coerce_fall_flag(raw.get("fall")):
        logger.warning(
            "VLM said fall but produced no events — check model JSON; raw keys: %s",
            list(raw.keys()) if isinstance(raw, dict) else type(raw),
        )
    else:
        logger.info(
            "VLM: no fall for %s (confidence in response: %s)",
            name,
            raw.get("confidence") if isinstance(raw, dict) else None,
        )
    return events


def analyze_clip(mp4_bytes: bytes) -> list[dict[str, Any]]:
    """
    Analyze raw MP4 bytes. Returns event dicts compatible with segment_receiver:
      video, frame, timestamp, type, magnitude, blur  (+ optional brief)
    """
    cfg = _config_from_env()
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    try:
        try:
            os.write(fd, mp4_bytes)
        finally:
            os.close(fd)
        return analyze_video_file(tmp, cfg)
    except Exception as exc:
        logger.error("analyze_clip error: %s", exc)
        return []
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── Folder runner (batch) ─────────────────────────────────────────────────────
class FolderFallDetector:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or _config_from_env()

    def _find_videos(self) -> list[Path]:
        folder = Path(self.cfg.input_folder)
        if not folder.exists():
            raise FileNotFoundError(f"Input folder not found: {folder}")
        videos = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix in SUPPORTED_EXTENSIONS
        )
        if not videos:
            raise FileNotFoundError(
                f"No supported videos in {folder}\n"
                f"Extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        return videos

    def run(self) -> dict[str, list[dict[str, Any]]]:
        videos = self._find_videos()
        out_dir = Path(self.cfg.output_folder)
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Found %d video(s) in %s", len(videos), self.cfg.input_folder)
        all_events: dict[str, list[dict[str, Any]]] = {}
        t0 = time.time()
        for i, vp in enumerate(videos, 1):
            logger.info("  %d. %s", i, vp.name)
            try:
                all_events[vp.name] = analyze_video_file(str(vp), self.cfg)
                summary = out_dir / f"{vp.stem}_vlm_events.json"
                summary.write_text(json.dumps(all_events[vp.name], indent=2), encoding="utf-8")
            except Exception as e:
                logger.error("  Failed %s: %s", vp.name, e)
                all_events[vp.name] = []

        logger.info("Done in %.1fs — see %s", time.time() - t0, out_dir)
        return all_events


if __name__ == "__main__":
    detector = FolderFallDetector(_config_from_env())
    detector.run()
