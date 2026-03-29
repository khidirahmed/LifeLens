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
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

import websockets


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
        out_dir: Path | None,
        segment_seconds: float = 30.0,
        fps: float = 24.0,
        quiet: bool = False,
    ) -> None:
        if not upload_url and not out_dir:
            raise ValueError("SegmentRecorder needs upload_url and/or out_dir")
        self._upload_url = upload_url
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

        if self._upload_url:
            try:
                _http_post_mp4(self._upload_url, data, idx, self._quiet)
            except RuntimeError as e:
                if not self._quiet:
                    print(f"[!] {e}")

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

                if preview is not None:
                    preview.update_jpeg(message)

                if latest_path is not None:
                    latest_path.write_bytes(message)

                if record_dir is not None:
                    record_dir.mkdir(parents=True, exist_ok=True)
                    dest = record_dir / f"frame_{saved_count:06d}.jpg"
                    dest.write_bytes(message)
                    saved_count += 1

                if segment_recorder is not None:
                    segment_recorder.write_jpeg(message, now)

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
    p = argparse.ArgumentParser(description="RayBanStream WebSocket JPEG receiver")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--latest", default="latest.jpg", help="Empty string to disable writing latest.jpg")
    p.add_argument("--record-dir", default="", help="Save every JPEG frame as frame_NNNNNN.jpg")
    p.add_argument(
        "--send-segment-url",
        default="",
        help="HTTP POST each completed MP4 here (body = raw video/mp4). No local save unless --segment-dir",
    )
    p.add_argument(
        "--segment-dir",
        default="",
        help="Also save a copy of each MP4 segment to this directory (optional)",
    )
    p.add_argument(
        "--no-segments",
        action="store_true",
        help="Disable MP4 segment encode/upload entirely (preview + relay only)",
    )
    p.add_argument(
        "--segment-seconds",
        type=float,
        default=30.0,
        help="Length of each recording file in seconds (default 30)",
    )
    p.add_argument(
        "--segment-fps",
        type=float,
        default=24.0,
        help="FPS passed to VideoWriter (default 24, match glasses stream)",
    )
    p.add_argument("--no-display", action="store_true", help="No OpenCV window (server only)")
    p.add_argument("--quiet", action="store_true")
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
    if want_segments:
        segment_recorder = SegmentRecorder(
            upload_url=send_url,
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
        if send_url:
            print(f"  MP4 upload: POST -> {send_url} (~every {args.segment_seconds:g}s)")
        if segment_dir is not None:
            print(f"  MP4 disk copy: {segment_dir}/")
    elif args.no_segments:
        print("  MP4 segments: off (--no-segments)")
    else:
        print(
            "  MP4 segments: off (pass --send-segment-url and/or --segment-dir to enable)"
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
