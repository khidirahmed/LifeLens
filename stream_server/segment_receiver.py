#!/usr/bin/env python3
"""
LifeLens segment receiver (run on the ASUS / analysis box over Tailscale).

Two channels:

  HTTP  (port 8788 default) — legacy one-way upload, backward-compatible.
    POST /meta    JSON: { kind, segment_index, byte_length, content_type }
    POST /segment raw video/mp4 body; header X-LifeLens-Segment-Index
                  Saves file then runs analyze_video.analyze_clip in a background thread.

  WebSocket  (port 8789 default) — CONSTANT BIDIRECTIONAL channel.
    relay_server.py connects here as a WebSocket client.
    Protocol (per segment):
      1. relay  -> receiver  TEXT  : JSON {"type":"segment","index":N,"size":B}
      2. relay  -> receiver  BINARY: raw MP4 bytes
      3. receiver -> relay   TEXT  : JSON {"type":"result","index":N,
                                           "fall":true|false,"events":[...]}
    If a fall is detected the result contains the event list so relay_server.py
    can log / alert immediately.

Usage (ASUS):
  pip install websockets
  python3 segment_receiver.py --host 0.0.0.0 --port 8788 --ws-port 8789

analyze_video.py must live one directory above this file (../analyze_video.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import websockets

# ── Import fall-detection library from parent directory ────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_ANALYSIS_ERR: str | None = None
try:
    from analyze_video import analyze_clip  # type: ignore
    _ANALYSIS_OK = True
except Exception as _imp_err:
    _ANALYSIS_OK = False
    _ANALYSIS_ERR = str(_imp_err)
    print(f"[!] analyze_video import failed — analysis disabled: {_imp_err}", file=sys.stderr)

    def analyze_clip(mp4_bytes: bytes) -> list:  # type: ignore
        return []


# ── Helpers ────────────────────────────────────────────────────────────────────
def _default_receive_dir() -> Path:
    env = os.environ.get("LIFELENS_RECEIVER_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "Documents" / "stream_server" / "received_segments").resolve()


def _print_fall_alert(idx: int, events: list) -> None:
    print(f"\n{'='*55}")
    print(f"  *** FALL DETECTED — segment #{idx} ***")
    for ev in events:
        print(
            f"  [{ev.get('type', '?').upper()}]  {ev.get('timestamp')}  "
            f"frame={ev.get('frame')}  mag={ev.get('magnitude')}"
        )
    print(f"{'='*55}\n")


def _analyze_http_segment_async(idx: int, mp4_bytes: bytes) -> None:
    """Run analyze_clip off the HTTP thread so POST /segment returns quickly."""
    if not _ANALYSIS_OK:
        return

    def _work() -> None:
        print(f"[http/analysis] segment #{idx} ({len(mp4_bytes)} B) — analysing...")
        try:
            events = analyze_clip(mp4_bytes)
        except Exception as exc:
            print(f"[!] analyze_clip failed (HTTP segment #{idx}): {exc}", file=sys.stderr)
            return
        if events:
            _print_fall_alert(idx, events)
        else:
            print(f"[http/analysis] segment #{idx} — no fall detected")

    threading.Thread(target=_work, name=f"analyze-http-{idx}", daemon=True).start()


# ── WebSocket server (constant bidirectional channel with relay_server.py) ─────
async def _ws_handle_relay(websocket) -> None:
    """
    One coroutine per connection from relay_server.py.
    Expects alternating TEXT (JSON meta) + BINARY (MP4 bytes) messages.
    Sends back a TEXT JSON result after each segment is analysed.
    """
    peer = websocket.remote_address
    print(f"[ws] relay_server.py connected from {peer}")
    pending_meta: dict | None = None

    try:
        async for message in websocket:
            if isinstance(message, str):
                # Metadata header for the next binary segment
                try:
                    pending_meta = json.loads(message)
                except json.JSONDecodeError:
                    print(f"[ws] bad JSON from relay: {message[:120]}")

            elif isinstance(message, bytes):
                idx = (pending_meta or {}).get("index", 0)
                pending_meta = None
                size = len(message)
                print(f"[ws] segment #{idx} received ({size} B) — analysing...")

                # Run fall detection in thread pool (CPU-heavy, must not block loop).
                try:
                    events = await asyncio.to_thread(analyze_clip, message)
                except Exception as exc:
                    print(f"[ws] analyze_clip error segment #{idx}: {exc}", file=sys.stderr)
                    events = []

                fall = len(events) > 0
                result = json.dumps({
                    "type": "result",
                    "index": idx,
                    "fall": fall,
                    "events": events,
                })
                await websocket.send(result)

                if fall:
                    _print_fall_alert(idx, events)
                else:
                    print(f"[ws] segment #{idx} — no fall detected")

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError as exc:
        print(f"[ws] relay disconnected with error: {exc}")
    finally:
        print(f"[ws] relay_server.py disconnected: {peer}")


async def _ws_serve(host: str, port: int) -> None:
    print(f"[ws] WebSocket channel ready  ws://{host}:{port}/")
    async with websockets.serve(
        _ws_handle_relay,
        host,
        port,
        max_size=None,      # segments can be several MB
        ping_interval=None, # relay_server.py sends continuous data — no ping needed
    ):
        await asyncio.Future()  # run forever


def _start_ws_thread(host: str, port: int) -> None:
    asyncio.run(_ws_serve(host, port))


# ── HTTP server (legacy one-way upload) ───────────────────────────────────────
class SegmentReceiverHandler(BaseHTTPRequestHandler):
    server_version = "LifeLensSegmentReceiver/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), fmt % args)
        )

    def _send(
        self,
        code: int,
        body: bytes | None = None,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if body is not None:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body is not None:
            self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        out_dir: Path = getattr(self.server, "lifelens_out_dir")

        length = self.headers.get("Content-Length")
        n = int(length) if length and length.isdigit() else 0
        raw = self.rfile.read(n) if n else b""

        if path == "/meta":
            try:
                obj = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                self._send(400, b"invalid JSON\n")
                return
            idx = obj.get("segment_index", "?")
            bl = obj.get("byte_length", "?")
            print(f"[http/meta] segment_index={idx} byte_length={bl} kind={obj.get('kind')!r}")
            self._send(200, b"ok\n")
            return

        if path == "/segment":
            idx_hdr = self.headers.get("X-LifeLens-Segment-Index", "0")
            try:
                idx = int(idx_hdr)
            except ValueError:
                idx = 0
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            dest = out_dir / f"lifelens_{ts}_{idx:04d}.mp4"
            try:
                dest.write_bytes(raw)
            except OSError as exc:
                print(f"[!] write failed: {exc}")
                self._send(500, str(exc).encode("utf-8", errors="replace"))
                return
            print(f"[http/segment] saved {len(raw)} B -> {dest}")
            _analyze_http_segment_async(idx, raw)
            self._send(200, b"ok\n")
            return

        self._send(404, b"use POST /meta or POST /segment\n")


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(
        description="Receive LifeLens MP4 segments — HTTP + WebSocket (Tailscale-friendly)"
    )
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8788, help="HTTP port (legacy)")
    p.add_argument(
        "--ws-port",
        type=int,
        default=8789,
        help="WebSocket port for constant bidirectional channel with relay_server.py (default 8789)",
    )
    p.add_argument(
        "--dir",
        default=str(_default_receive_dir()),
        help="Directory for .mp4 files saved via HTTP (default: ~/Documents/stream_server/received_segments)",
    )
    args = p.parse_args()

    out_dir = Path(args.dir).expanduser().resolve()

    # Start WebSocket server in a background daemon thread.
    ws_thread = threading.Thread(
        target=_start_ws_thread,
        args=(args.host, args.ws_port),
        name="ws-server",
        daemon=True,
    )
    ws_thread.start()

    # Start legacy HTTP server on main thread.
    httpd = ThreadingHTTPServer((args.host, args.port), SegmentReceiverHandler)
    httpd.lifelens_out_dir = out_dir

    print("LifeLens segment receiver")
    print(f"  HTTP  (legacy):  http://{args.host}:{args.port}/")
    print(f"    POST /meta    — JSON segment preview")
    print(f"    POST /segment — raw video/mp4 upload")
    print(f"  WebSocket (live): ws://{args.host}:{args.ws_port}/")
    print(f"    Bidirectional — relay sends segments, receiver sends analysis results")
    if _ANALYSIS_OK:
        print(f"  Analysis: enabled (analyze_video.py)")
    else:
        print(f"  Analysis: DISABLED — {_ANALYSIS_ERR}")
    print(f"  Saving HTTP segments to: {out_dir}/")
    print()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
