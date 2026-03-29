#!/usr/bin/env python3
"""
WebSocket JPEG receiver for RayBanStream.

macOS: OpenCV windows must run on the **main thread**. This script runs the
asyncio WebSocket server in a **background thread** and the preview loop on
the main thread (same pattern as python-receiver/receiver.py).

Usage:
  cd stream_server && source .venv/bin/activate && pip install -r requirements.txt
  python relay_server.py

Or use --no-display for headless (no OpenCV).
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import threading
import time
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
        print(f"[-] Disconnected {peer}  (frames={frame_count})")


async def _serve_forever(
    host: str,
    port: int,
    latest_path: Path | None,
    record_dir: Path | None,
    preview: FramePreview | None,
    quiet: bool,
) -> None:
    async with websockets.serve(
        lambda ws: _client_handler(
            ws,
            latest_path=latest_path,
            record_dir=record_dir,
            preview=preview,
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
    quiet: bool,
) -> None:
    asyncio.run(
        _serve_forever(host, port, latest_path, record_dir, preview, quiet)
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RayBanStream WebSocket JPEG receiver")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--latest", default="latest.jpg", help="Empty string to disable writing latest.jpg")
    p.add_argument("--record-dir", default="", help="Save frames to this directory")
    p.add_argument("--no-display", action="store_true", help="No OpenCV window (server only)")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    latest_path = Path(args.latest).resolve() if args.latest else None
    record_dir = Path(args.record_dir).resolve() if args.record_dir else None

    lan = _guess_lan_ip()
    print("RayBan stream server")
    print(f"  Listening:  ws://{args.host}:{args.port}")
    print(f"  iPhone URL (guess):  ws://{lan}:{args.port}")
    if latest_path:
        print(f"  Latest frame file: {latest_path}")
    if record_dir:
        print(f"  Recording to: {record_dir}/")

    if args.no_display:
        print("  (no display)\n")
        try:
            asyncio.run(
                _serve_forever(
                    args.host, args.port, latest_path, record_dir, None, args.quiet
                )
            )
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        try:
            import cv2  # noqa: F401
        except ImportError:
            raise SystemExit("Install opencv-python or use --no-display") from None

        preview = FramePreview()
        th = threading.Thread(
            target=_run_server_thread,
            args=(args.host, args.port, latest_path, record_dir, preview, args.quiet),
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
