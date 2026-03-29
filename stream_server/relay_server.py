#!/usr/bin/env python3
"""
WebSocket JPEG receiver for RayBanStream.

macOS: OpenCV windows must run on the **main thread**. This script runs the
asyncio WebSocket server in a **background thread** and the preview loop on
the main thread (same pattern as python-receiver/receiver.py).

Usage:
  cd stream_server && source .venv/bin/activate && pip install -r requirements.txt
  python relay_server.py

MP4 segments are not saved locally by default. Use --send-segment-url to HTTP POST each
completed segment (~every 30s). Optional --segment-dir also writes a copy to disk.
Use --no-display for headless (no OpenCV window).

Phone / glasses connect to this Mac on your LAN (same Wi-Fi): ws://<LAN-IP>:<port>.
That does not use Tailscale. Tailscale IPs in .env are only for this Mac → ASUS
(segment_receiver): LIFELENS_SEND_SEGMENT_URL, LIFELENS_RECEIVER_WS, etc.

Environment (stream_server/.env and repo-root .env):
  LIFELENS_HOST, LIFELENS_PORT, LIFELENS_ADVERTISE_IP (optional override for printed phone URL),
  LIFELENS_LATEST, LIFELENS_RECORD_DIR,
  LIFELENS_SEND_SEGMENT_URL, LIFELENS_SEND_SEGMENT_META_URL, LIFELENS_SEGMENT_DIR,
  LIFELENS_RECEIVER_WS, LIFELENS_SEGMENT_SECONDS, LIFELENS_SEGMENT_FPS,
  LIFELENS_NO_SEGMENTS, LIFELENS_NO_DISPLAY, LIFELENS_QUIET (true/1/yes)
  Retell (outbound call on fall when LIFELENS_RECEIVER_WS is used): RETELL_API_KEY,
  RETELL_FROM_NUMBER, RETELL_TO_NUMBER, optional RETELL_AGENT_ID, RETELL_DISABLE
CLI flags override .env defaults when provided.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

import websockets

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lifelens_retell import events_to_alert_message, send_retell_fall_call


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)


def _env_str(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v is None:
        return default
    return str(v).strip()


def _env_int(key: str, default: int) -> int:
    v = _env_str(key)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    v = _env_str(key)
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _env_bool(key: str) -> bool:
    return _env_str(key).lower() in ("1", "true", "yes", "on")


def _guess_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _is_jpeg(data: bytes) -> bool:
    return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"


def _is_image_bytes(data: bytes) -> bool:
    """
    True if OpenCV can decode this buffer as an image (JPEG, PNG, etc.).
    Matches python-receiver/receiver.py — the Meta app may send non-JPEG
    binary; strict JPEG-only checks yield frames=0 while the socket is alive.
    """
    if len(data) < 10:
        return False
    if _is_jpeg(data):
        return True
    try:
        import cv2
        import numpy as np
    except ImportError:
        return False
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR) is not None


# ── Persistent WebSocket client to segment_receiver.py ─────────────────────────
class ReceiverLink:
    """
    Maintains a long-lived WebSocket connection from relay_server.py (Mac)
    to segment_receiver.py (ASUS) for constant bidirectional communication.

    Outbound (relay → receiver):
      TEXT  JSON {"type":"segment","index":N,"size":B}
      BINARY raw MP4 bytes

    Inbound (receiver → relay):
      TEXT  JSON {"type":"result","index":N,"fall":bool,"events":[...]}

    Call submit_segment() from any thread (SegmentRecorder worker).
    Call run() as an asyncio task inside _serve_forever().
    """

    def __init__(self, url: str, quiet: bool) -> None:
        self._url = url
        self._quiet = quiet
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Thread-safe entry point ────────────────────────────────────────────────
    def submit_segment(self, index: int, data: bytes) -> None:
        """Called from SegmentRecorder thread — enqueues segment for WebSocket send."""
        if self._loop is None or self._queue is None:
            return
        asyncio.run_coroutine_threadsafe(self._queue.put((index, data)), self._loop)

    # ── Async main loop ────────────────────────────────────────────────────────
    async def run(self) -> None:
        """Long-running task — reconnects automatically if ASUS drops."""
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        while True:
            try:
                async with websockets.connect(
                    self._url,
                    max_size=None,
                    ping_interval=None,  # segments are the heartbeat
                ) as ws:
                    if not self._quiet:
                        print(f"[->receiver] Connected to segment_receiver.py at {self._url}")
                    send_t = asyncio.create_task(self._send_loop(ws))
                    recv_t = asyncio.create_task(self._recv_loop(ws))
                    done, pending = await asyncio.wait(
                        [send_t, recv_t], return_when=asyncio.FIRST_EXCEPTION
                    )
                    for t in pending:
                        t.cancel()
                    for t in done:
                        exc = t.exception()
                        if exc:
                            raise exc
            except Exception as exc:
                if not self._quiet:
                    print(f"[->receiver] Disconnected ({exc}) — retrying in 5 s")
                await asyncio.sleep(5)

    async def _send_loop(self, ws) -> None:
        """Drain the segment queue and send each one as meta + binary."""
        while True:
            index, data = await self._queue.get()
            meta = json.dumps({"type": "segment", "index": index, "size": len(data)})
            await ws.send(meta)
            await ws.send(data)
            if not self._quiet:
                print(f"[->receiver] Sent segment #{index} ({len(data)} B) via WebSocket")

    async def _recv_loop(self, ws) -> None:
        """Handle analysis results coming back from segment_receiver.py."""
        async for message in ws:
            if not isinstance(message, str):
                continue
            try:
                obj = json.loads(message)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "result":
                continue
            idx = obj.get("index", "?")
            events = obj.get("events", [])
            if obj.get("fall"):
                print(f"\n{'='*55}")
                print(f"  *** FALL DETECTED — segment #{idx} ***")
                ev_list = events if isinstance(events, list) else []
                for ev in ev_list:
                    print(
                        f"  [{ev.get('type','?').upper()}]  {ev.get('timestamp')}  "
                        f"frame={ev.get('frame')}  mag={ev.get('magnitude')}"
                    )
                print(f"{'='*55}\n")
                msg = events_to_alert_message(ev_list)
                clip_name = f"segment_{idx}.mp4"
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    functools.partial(send_retell_fall_call, msg, clip_name=clip_name),
                )
            elif not self._quiet:
                print(f"[->receiver] Segment #{idx} — no fall detected")


def _http_post_json(url: str, payload: dict, quiet: bool) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if not quiet:
                print(f"[+] Segment meta -> HTTP {resp.status} ({url})")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta POST failed: HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Meta POST failed: {e.reason}") from e


def _http_post_mp4(url: str, data: bytes, segment_index: int, quiet: bool) -> None:
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "video/mp4")
    req.add_header("X-LifeLens-Segment-Index", str(segment_index))
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            if not quiet:
                print(
                    f"[+] Sent MP4 segment #{segment_index} ({len(data)} B) -> HTTP {resp.status}"
                )
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upload failed: HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Upload failed: {e.reason}") from e


class SegmentRecorder:
    """Encodes JPEG frames to MP4 in a temp file, then uploads and/or copies to disk."""

    def __init__(
        self,
        *,
        upload_url: str | None,
        meta_url: str | None,
        out_dir: Path | None,
        segment_seconds: float = 30.0,
        fps: float = 24.0,
        quiet: bool = False,
        receiver_link: "ReceiverLink | None" = None,
    ) -> None:
        if not upload_url and not out_dir and receiver_link is None:
            raise ValueError("SegmentRecorder needs upload_url, out_dir, or receiver_link")
        self._upload_url = upload_url
        self._meta_url = (meta_url or "").strip() or None
        self._dir = out_dir
        self._segment = float(segment_seconds)
        self._fps = fps
        self._quiet = quiet
        self._receiver_link = receiver_link  # WebSocket channel to segment_receiver.py
        self._lock = threading.Lock()
        self._writer = None
        self._current_path: Path | None = None
        self._segment_start: float | None = None
        self._size: tuple[int, int] | None = None
        self._segment_index = 0
        self._mp4_disabled = False

    def _finalize_segment_file(self) -> None:
        """Close writer, upload/copy MP4, delete temp file."""
        if self._writer is None or self._current_path is None:
            return

        self._writer.release()
        self._writer = None
        path = self._current_path
        self._current_path = None

        try:
            data = path.read_bytes()
        except OSError as e:
            if not self._quiet:
                print(f"[!] Could not read segment file: {e}")
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return

        idx = self._segment_index
        self._segment_index += 1

        if self._meta_url:
            try:
                _http_post_json(
                    self._meta_url,
                    {
                        "kind": "segment_complete",
                        "segment_index": idx,
                        "byte_length": len(data),
                        "content_type": "video/mp4",
                    },
                    self._quiet,
                )
            except RuntimeError as e:
                if not self._quiet:
                    print(f"[!] {e}")

        if self._upload_url:
            try:
                _http_post_mp4(self._upload_url, data, idx, self._quiet)
            except RuntimeError as e:
                if not self._quiet:
                    print(f"[!] {e}")

        # WebSocket channel — send to segment_receiver.py for analysis + feedback.
        # submit_segment() is thread-safe; result comes back via ReceiverLink._recv_loop.
        if self._receiver_link is not None:
            self._receiver_link.submit_segment(idx, data)

        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            dest = self._dir / f"lifelens_{ts}_{idx:04d}.mp4"
            try:
                shutil.copyfile(path, dest)
                if not self._quiet:
                    print(f"[+] Saved copy: {dest}")
            except OSError as e:
                if not self._quiet:
                    print(f"[!] Could not save segment copy: {e}")

        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _open_writer(self, w: int, h: int) -> None:
        import cv2

        if self._writer is not None:
            self._finalize_segment_file()

        fd, raw = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        path = Path(raw)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, self._fps, (w, h))
        if not writer.isOpened():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(
                "OpenCV could not open MP4 writer (temp file). "
                "Check codec support or use --no-segments."
            )
        self._writer = writer
        self._current_path = path
        self._size = (w, h)
        if not self._quiet:
            where = []
            if self._meta_url:
                where.append(f"meta {self._meta_url}")
            if self._upload_url:
                where.append(f"upload {self._upload_url}")
            if self._dir is not None:
                where.append(f"copy {self._dir}/")
            print(f"[+] MP4 segment {self._segment_index} -> {' + '.join(where)} (~{self._segment:g}s)")

    def write_jpeg(self, jpeg_bytes: bytes, now: float) -> None:
        import cv2
        import numpy as np

        if self._mp4_disabled:
            return

        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return
        h, w = frame.shape[:2]

        with self._lock:
            elapsed = (
                (now - self._segment_start)
                if self._segment_start is not None
                else 0.0
            )
            need_new = (
                self._writer is None
                or self._size != (w, h)
                or elapsed >= self._segment
            )
            if need_new:
                try:
                    self._open_writer(w, h)
                except RuntimeError as e:
                    if not self._quiet:
                        print(f"[!] {e}")
                    self._mp4_disabled = True
                    return
                self._segment_start = now

            if self._size and (w, h) != self._size:
                frame = cv2.resize(frame, self._size)

            if self._writer is not None:
                self._writer.write(frame)

    def close(self) -> None:
        with self._lock:
            if self._writer is not None:
                self._finalize_segment_file()
            self._size = None
            self._segment_start = None
        if not self._quiet:
            print("[+] Segment pipeline closed")


class FramePreview:
    __slots__ = ("_lock", "_jpeg")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None

    def update_jpeg(self, data: bytes) -> None:
        with self._lock:
            self._jpeg = data

    def copy_jpeg(self) -> bytes | None:
        with self._lock:
            return None if self._jpeg is None else bytes(self._jpeg)


def _preview_window_loop(title: str, preview: FramePreview) -> None:
    """Must run on the main thread (macOS / OpenCV)."""
    import numpy as np
    import cv2

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    h, w = 360, 640
    cv2.resizeWindow(title, w, h)

    waiting = np.zeros((h, w, 3), dtype=np.uint8)
    waiting[:] = (24, 30, 42)
    cv2.putText(
        waiting, "Connect phone & start stream", (60, h // 2 - 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA,
    )
    cv2.putText(
        waiting, "Q = close preview", (200, h // 2 + 24),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (140, 140, 160), 1, cv2.LINE_AA,
    )

    while True:
        jpeg = preview.copy_jpeg()
        if jpeg is not None:
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                cv2.imshow(title, frame)
        else:
            cv2.imshow(title, waiting)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q")):
            break

    try:
        cv2.destroyWindow(title)
    except cv2.error:
        pass


async def _client_handler(
    websocket,
    *,
    latest_path: Path | None,
    record_dir: Path | None,
    preview: FramePreview | None,
    segment_recorder: SegmentRecorder | None,
    quiet: bool,
) -> None:
    peer = websocket.remote_address
    print(f"[+] Client connected: {peer}")
    frame_count = 0
    saved_count = 0
    times: deque[float] = deque(maxlen=30)
    t_last_log = time.monotonic()
    loop = asyncio.get_running_loop()

    # Pre-create record_dir once so mkdir isn't called on every frame.
    if record_dir is not None:
        record_dir.mkdir(parents=True, exist_ok=True)

    try:
        async for message in websocket:
            now = time.monotonic()
            if isinstance(message, bytes):
                if not _is_image_bytes(message):
                    if not quiet:
                        head = message[:12].hex() if len(message) >= 12 else message.hex()
                        print(
                            f"[!] Binary {len(message)} B — OpenCV cannot decode as image (hex {head})"
                        )
                    continue
                frame_count += 1
                times.append(now)

                # preview.update_jpeg is just a lock + bytes swap — fast, fine on loop.
                if preview is not None:
                    preview.update_jpeg(message)

                # All disk/CPU work is fire-and-forget into the thread pool.
                # The receive loop must never block, or WebSocket pings time out
                # and the connection drops with "no close frame received or sent".
                if latest_path is not None:
                    loop.run_in_executor(None, latest_path.write_bytes, message)

                if record_dir is not None:
                    dest = record_dir / f"frame_{saved_count:06d}.jpg"
                    saved_count += 1
                    loop.run_in_executor(None, dest.write_bytes, message)

                # write_jpeg does JPEG decode + H264 VideoWriter.write — CPU-heavy.
                # Running it synchronously on the event loop blocks pong handling.
                if segment_recorder is not None:
                    loop.run_in_executor(None, segment_recorder.write_jpeg, message, now)

                if not quiet and now - t_last_log >= 1.0:
                    t_last_log = now
                    fps = len(times) / (times[-1] - times[0]) if len(times) > 1 else 0.0
                    print(f"    frames={frame_count}  ~{fps:.1f} fps  last={len(message)} B")
            elif isinstance(message, str):
                snippet = message if len(message) <= 240 else (message[:240] + "…")
                print(f"    text from client: {snippet!r}")
            else:
                print(f"[!] Unexpected message type: {type(message)}")
    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[-] Client closed with error: {e}")
    finally:
        if segment_recorder is not None:
            segment_recorder.close()
        if frame_count == 0:
            print(
                f"[-] Disconnected {peer}  (frames=0 — start live stream in the Ray-Ban Meta app; "
                "URL must be ws://<this Mac's Wi-Fi IP>:<port>. If you see 'cannot decode' lines, the wire format changed.)"
            )
        else:
            print(f"[-] Disconnected {peer}  (frames={frame_count})")


async def _serve_forever(
    host: str,
    port: int,
    latest_path: Path | None,
    record_dir: Path | None,
    preview: FramePreview | None,
    segment_recorder: SegmentRecorder | None,
    receiver_link: "ReceiverLink | None",
    quiet: bool,
) -> None:
    # If a ReceiverLink is configured, start it as a background task so it
    # maintains a persistent WebSocket connection to segment_receiver.py.
    if receiver_link is not None:
        asyncio.create_task(receiver_link.run())

    async with websockets.serve(
        lambda ws: _client_handler(
            ws,
            latest_path=latest_path,
            record_dir=record_dir,
            preview=preview,
            segment_recorder=segment_recorder,
            quiet=quiet,
        ),
        host,
        port,
        max_size=None,
        # Disable server-side pings. The 24 fps frame stream is its own
        # heartbeat. With the default ping_interval=20 / ping_timeout=20,
        # any event-loop stall >20 s triggers "no close frame received or sent".
        ping_interval=None,
    ):
        await asyncio.Future()


def _run_server_thread(
    host: str,
    port: int,
    latest_path: Path | None,
    record_dir: Path | None,
    preview: FramePreview | None,
    segment_recorder: SegmentRecorder | None,
    receiver_link: "ReceiverLink | None",
    quiet: bool,
) -> None:
    asyncio.run(
        _serve_forever(
            host, port, latest_path, record_dir, preview,
            segment_recorder, receiver_link, quiet,
        )
    )


def _parse_args() -> argparse.Namespace:
    _load_dotenv()
    p = argparse.ArgumentParser(description="RayBanStream WebSocket JPEG receiver")
    p.add_argument(
        "--host",
        default=_env_str("LIFELENS_HOST", "0.0.0.0") or "0.0.0.0",
    )
    p.add_argument("--port", type=int, default=_env_int("LIFELENS_PORT", 8765))
    p.add_argument(
        "--advertise-ip",
        default=_env_str("LIFELENS_ADVERTISE_IP", ""),
        help=(
            "IP shown for the phone/glasses WebSocket URL (default: guessed LAN). "
            "Use if the guess is wrong. Phone uses same Wi-Fi as this Mac — not Tailscale."
        ),
    )
    p.add_argument(
        "--latest",
        default=_env_str("LIFELENS_LATEST", "latest.jpg"),
        help="Empty string to disable writing latest.jpg",
    )
    p.add_argument(
        "--record-dir",
        default=_env_str("LIFELENS_RECORD_DIR", ""),
        help="Save every JPEG frame as frame_NNNNNN.jpg",
    )
    p.add_argument(
        "--send-segment-url",
        default=_env_str("LIFELENS_SEND_SEGMENT_URL", ""),
        help="HTTP POST each completed MP4 here (body = raw video/mp4). Use Tailscale IP, e.g. http://100.x.x.x:8788/segment",
    )
    p.add_argument(
        "--send-segment-meta-url",
        default=_env_str("LIFELENS_SEND_SEGMENT_META_URL", ""),
        help="Optional: HTTP POST JSON first (segment_index, byte_length) before each MP4 — pair with segment_receiver.py /meta",
    )
    p.add_argument(
        "--segment-dir",
        default=_env_str("LIFELENS_SEGMENT_DIR", ""),
        help="Also save a copy of each MP4 segment to this directory (optional)",
    )
    p.add_argument(
        "--no-segments",
        action="store_true",
        default=_env_bool("LIFELENS_NO_SEGMENTS"),
        help="Disable MP4 segment encode/upload entirely (preview + relay only)",
    )
    p.add_argument(
        "--segment-seconds",
        type=float,
        default=_env_float("LIFELENS_SEGMENT_SECONDS", 30.0),
        help="Length of each recording file in seconds (default 30)",
    )
    p.add_argument(
        "--segment-fps",
        type=float,
        default=_env_float("LIFELENS_SEGMENT_FPS", 24.0),
        help="FPS passed to VideoWriter (default 24, match glasses stream)",
    )
    p.add_argument(
        "--no-display",
        action="store_true",
        default=_env_bool("LIFELENS_NO_DISPLAY"),
        help="No OpenCV window (server only)",
    )
    p.add_argument(
        "--receiver-ws",
        default=_env_str("LIFELENS_RECEIVER_WS", ""),
        help=(
            "WebSocket URL of segment_receiver.py for constant bidirectional communication "
            "(e.g. ws://100.x.x.x:8789). "
            "Segments are sent here for analysis; fall results come back over the same connection. "
            "Set LIFELENS_RECEIVER_WS in .env or pass this flag."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        default=_env_bool("LIFELENS_QUIET"),
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    latest_path = Path(args.latest).resolve() if args.latest else None
    record_dir = Path(args.record_dir).resolve() if args.record_dir else None

    send_url = (args.send_segment_url or "").strip() or None
    seg_dir_raw = (args.segment_dir or "").strip()
    segment_dir: Path | None = Path(seg_dir_raw).resolve() if seg_dir_raw else None
    receiver_ws_url = (args.receiver_ws or "").strip() or None

    # ReceiverLink — persistent WebSocket client to segment_receiver.py.
    receiver_link: ReceiverLink | None = None
    if receiver_ws_url:
        receiver_link = ReceiverLink(url=receiver_ws_url, quiet=args.quiet)

    meta_url = (args.send_segment_meta_url or "").strip() or None
    want_segments = not args.no_segments and (
        send_url is not None or segment_dir is not None or receiver_link is not None
    )
    segment_recorder: SegmentRecorder | None = None
    if want_segments:
        segment_recorder = SegmentRecorder(
            upload_url=send_url,
            meta_url=meta_url,
            out_dir=segment_dir,
            segment_seconds=args.segment_seconds,
            fps=args.segment_fps,
            quiet=args.quiet,
            receiver_link=receiver_link,
        )

    phone_ip = (args.advertise_ip or "").strip() or _guess_lan_ip()
    print("RayBan stream server")
    print(f"  Listening:  ws://{args.host}:{args.port}")
    print(f"  Phone / glasses URL:  ws://{phone_ip}:{args.port}  (LAN — same Wi-Fi; Tailscale not used)")
    if not (args.advertise_ip or "").strip():
        print(f"    (LAN guessed as {phone_ip}; set LIFELENS_ADVERTISE_IP or --advertise-ip if wrong)")
    if latest_path:
        print(f"  Latest frame file: {latest_path}")
    if record_dir:
        print(f"  JPEG frames: {record_dir}/")
    if segment_recorder is not None:
        if meta_url:
            print(f"  MP4 meta: POST JSON -> {meta_url} (before each segment)")
        if send_url:
            print(f"  MP4 upload: POST -> {send_url} (~every {args.segment_seconds:g}s)")
        if segment_dir is not None:
            print(f"  MP4 disk copy: {segment_dir}/")
        if receiver_link is not None:
            print(f"  WebSocket -> segment_receiver: {receiver_ws_url}  (bidirectional, analysis results back)")
        for label, u in (("meta", meta_url), ("upload", send_url), ("receiver-ws", receiver_ws_url)):
            if u and "x.x.x" in u:
                print(
                    f"  [!] {label} URL looks like a placeholder — set a real Tailscale IP in .env "
                    f"(run `tailscale ip -4` on the ASUS). Errno 8 means DNS cannot resolve the host."
                )
                break
    elif args.no_segments:
        print("  MP4 segments: off (--no-segments)")
    else:
        print(
            "  MP4 segments: off (set LIFELENS_RECEIVER_WS / LIFELENS_SEND_SEGMENT_URL in .env,"
            " or pass --receiver-ws / --send-segment-url)"
        )

    if args.no_display:
        print("  (no display)\n")
        try:
            asyncio.run(
                _serve_forever(
                    args.host,
                    args.port,
                    latest_path,
                    record_dir,
                    None,
                    segment_recorder,
                    receiver_link,
                    args.quiet,
                )
            )
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            if segment_recorder is not None:
                segment_recorder.close()
    else:
        try:
            import cv2  # noqa: F401
        except ImportError:
            raise SystemExit("Install opencv-python or use --no-display") from None

        preview = FramePreview()
        th = threading.Thread(
            target=_run_server_thread,
            args=(
                args.host,
                args.port,
                latest_path,
                record_dir,
                preview,
                segment_recorder,
                receiver_link,
                args.quiet,
            ),
            name="relay-websocket",
            daemon=False,
        )
        th.start()
        time.sleep(0.15)
        print("  Live preview: OpenCV on main thread (Q closes window; server keeps running)\n")

        try:
            # ASCII title only — some OpenCV/macOS builds choke on Unicode in window names.
            _preview_window_loop("LifeLens relay preview", preview)
        except Exception as e:
            print(f"OpenCV error: {e}. Try: python relay_server.py --no-display")
            raise SystemExit(1) from e

        print("Preview closed. Server still running — Ctrl+C to stop.\n")
        try:
            th.join()
        except KeyboardInterrupt:
            print("\nStopped.")
