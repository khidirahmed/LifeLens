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
completed segment (~every 30s). Uploads run in a background thread so the WebSocket stream
is not blocked. Optional --send-segment-meta-url and --segment-dir.
Use --no-display for headless (no OpenCV window).

Tailscale: set URLs in stream_server/.env (LIFELENS_SEND_SEGMENT_URL, etc.) or use CLI flags.
See segment_receiver.py on the receiver host.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

import websockets


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parent / ".env")


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


def _segment_upload_job(
    meta_url: str | None,
    upload_url: str | None,
    data: bytes,
    idx: int,
    quiet: bool,
) -> None:
    """HTTP POST meta + MP4 (called from I/O worker)."""
    if meta_url:
        try:
            _http_post_json(
                meta_url,
                {
                    "kind": "segment_complete",
                    "segment_index": idx,
                    "byte_length": len(data),
                    "content_type": "video/mp4",
                },
                quiet,
            )
        except RuntimeError as e:
            if not quiet:
                print(f"[!] {e}")
    if upload_url:
        try:
            _http_post_mp4(upload_url, data, idx, quiet)
        except RuntimeError as e:
            if not quiet:
                print(f"[!] {e}")


def _segment_finalize_worker(
    path_str: str,
    idx: int,
    out_dir_str: str | None,
    meta_url: str | None,
    upload_url: str | None,
    quiet: bool,
) -> None:
    """Read MP4 from disk, optional local copy, HTTP upload, unlink — never blocks WebSocket loop."""
    path = Path(path_str)
    try:
        data = path.read_bytes()
    except OSError as e:
        if not quiet:
            print(f"[!] Could not read segment file: {e}")
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    if out_dir_str:
        out_dir = Path(out_dir_str)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = out_dir / f"lifelens_{ts}_{idx:04d}.mp4"
        try:
            shutil.copyfile(path, dest)
            if not quiet:
                print(f"[+] Saved copy: {dest}")
        except OSError as e:
            if not quiet:
                print(f"[!] Could not save segment copy: {e}")

    if meta_url or upload_url:
        _segment_upload_job(meta_url, upload_url, data, idx, quiet)

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


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
    ) -> None:
        if not upload_url and not out_dir:
            raise ValueError("SegmentRecorder needs upload_url and/or out_dir")
        self._upload_url = upload_url
        self._meta_url = (meta_url or "").strip() or None
        self._dir = out_dir
        self._segment = float(segment_seconds)
        self._fps = fps
        self._quiet = quiet
        self._lock = threading.Lock()
        self._writer = None
        self._current_path: Path | None = None
        self._segment_start: float | None = None
        self._size: tuple[int, int] | None = None
        self._segment_index = 0
        self._mp4_disabled = False
        # Single worker: read/copy/upload/unlink off the asyncio thread entirely.
        self._segment_io_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="lifelens-segment-io",
        )

    def _finalize_segment_file(self) -> None:
        """Close writer; heavy I/O runs in _segment_finalize_worker (does not block WebSocket)."""
        if self._writer is None or self._current_path is None:
            return

        self._writer.release()
        self._writer = None
        path = self._current_path
        self._current_path = None

        idx = self._segment_index
        self._segment_index += 1
        out_dir_str = str(self._dir) if self._dir is not None else None

        self._segment_io_executor.submit(
            _segment_finalize_worker,
            str(path),
            idx,
            out_dir_str,
            self._meta_url,
            self._upload_url,
            self._quiet,
        )

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
        self._segment_io_executor.shutdown(wait=True)
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

    # Pre-create record_dir once so we don't call mkdir inside the hot loop.
    if record_dir is not None:
        record_dir.mkdir(parents=True, exist_ok=True)

    try:
        async for message in websocket:
            now = time.monotonic()
            if isinstance(message, bytes):
                if not _is_jpeg(message):
                    if not quiet:
                        print(f"[!] Binary chunk {len(message)} B (not JPEG header)")
                    continue
                frame_count += 1
                times.append(now)

                # preview.update_jpeg is a single lock + bytes assign — fast, safe on loop.
                if preview is not None:
                    preview.update_jpeg(message)

                # All disk/CPU work runs in the default thread-pool executor WITHOUT
                # await so this receive loop is never blocked.  The TCP window stays
                # open and iOS never sees a freeze.
                if latest_path is not None:
                    loop.run_in_executor(None, latest_path.write_bytes, message)

                if record_dir is not None:
                    dest = record_dir / f"frame_{saved_count:06d}.jpg"
                    saved_count += 1
                    loop.run_in_executor(None, dest.write_bytes, message)

                # segment_recorder.write_jpeg does JPEG decode + VideoWriter encode —
                # CPU-heavy.  Fire-and-forget into the thread pool; SegmentRecorder's
                # internal lock keeps frames ordered.
                if segment_recorder is not None:
                    loop.run_in_executor(None, segment_recorder.write_jpeg, message, now)

                if not quiet and now - t_last_log >= 1.0:
                    t_last_log = now
                    fps = len(times) / (times[-1] - times[0]) if len(times) > 1 else 0.0
                    print(f"    frames={frame_count}  ~{fps:.1f} fps  last={len(message)} B")
            elif isinstance(message, str):
                print(f"    status: {message}")
            else:
                print(f"[!] Unexpected message type: {type(message)}")
    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[-] Client closed with error: {e}")
    finally:
        if segment_recorder is not None:
            segment_recorder.close()
        print(f"[-] Disconnected {peer}  (frames={frame_count})")


async def _serve_forever(
    host: str,
    port: int,
    latest_path: Path | None,
    record_dir: Path | None,
    preview: FramePreview | None,
    segment_recorder: SegmentRecorder | None,
    quiet: bool,
) -> None:
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
    ):
        await asyncio.Future()


def _run_server_thread(
    host: str,
    port: int,
    latest_path: Path | None,
    record_dir: Path | None,
    preview: FramePreview | None,
    segment_recorder: SegmentRecorder | None,
    quiet: bool,
) -> None:
    asyncio.run(
        _serve_forever(
            host, port, latest_path, record_dir, preview, segment_recorder, quiet
        )
    )


def _parse_args() -> argparse.Namespace:
    _load_dotenv()
    p = argparse.ArgumentParser(description="RayBanStream WebSocket JPEG receiver")
    p.add_argument("--host", default=_env_str("LIFELENS_HOST", "0.0.0.0") or "0.0.0.0")
    p.add_argument("--port", type=int, default=_env_int("LIFELENS_PORT", 8765))
    p.add_argument("--latest", default=_env_str("LIFELENS_LATEST", "latest.jpg"), help="Empty string to disable latest.jpg")
    p.add_argument("--record-dir", default=_env_str("LIFELENS_RECORD_DIR", ""), help="Save JPEG frames here")
    p.add_argument(
        "--send-segment-url",
        default=_env_str("LIFELENS_SEND_SEGMENT_URL", ""),
        help="POST each MP4 here, e.g. http://100.x.x.x:8788/segment",
    )
    p.add_argument(
        "--send-segment-meta-url",
        default=_env_str("LIFELENS_SEND_SEGMENT_META_URL", ""),
        help="Optional POST JSON before each MP4 (segment_receiver /meta)",
    )
    p.add_argument(
        "--segment-dir",
        default=_env_str("LIFELENS_SEGMENT_DIR", ""),
        help="Optional: also save MP4 copies on this Mac",
    )
    p.add_argument(
        "--no-segments",
        action="store_true",
        default=_env_bool("LIFELENS_NO_SEGMENTS"),
        help="Disable MP4 encode/upload",
    )
    p.add_argument("--segment-seconds", type=float, default=_env_float("LIFELENS_SEGMENT_SECONDS", 30.0))
    p.add_argument("--segment-fps", type=float, default=_env_float("LIFELENS_SEGMENT_FPS", 24.0))
    p.add_argument(
        "--no-display",
        action="store_true",
        default=_env_bool("LIFELENS_NO_DISPLAY"),
        help="No OpenCV window",
    )
    p.add_argument("--quiet", action="store_true", default=_env_bool("LIFELENS_QUIET"))
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    latest_path = Path(args.latest).resolve() if args.latest else None
    record_dir = Path(args.record_dir).resolve() if args.record_dir else None

    send_url = (args.send_segment_url or "").strip() or None
    seg_dir_raw = (args.segment_dir or "").strip()
    segment_dir: Path | None = Path(seg_dir_raw).resolve() if seg_dir_raw else None

    want_segments = not args.no_segments and (send_url is not None or segment_dir is not None)
    segment_recorder: SegmentRecorder | None = None
    meta_url = (args.send_segment_meta_url or "").strip() or None
    if want_segments:
        segment_recorder = SegmentRecorder(
            upload_url=send_url,
            meta_url=meta_url,
            out_dir=segment_dir,
            segment_seconds=args.segment_seconds,
            fps=args.segment_fps,
            quiet=args.quiet,
        )

    lan = _guess_lan_ip()
    print("RayBan stream server")
    print(f"  Listening:  ws://{args.host}:{args.port}")
    print(f"  iPhone URL (guess):  ws://{lan}:{args.port}")
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
    elif args.no_segments:
        print("  MP4 segments: off (--no-segments)")
    else:
        print(
            "  MP4 segments: off (set LIFELENS_SEND_SEGMENT_URL in .env or pass --send-segment-url)"
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
