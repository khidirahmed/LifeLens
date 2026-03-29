#!/usr/bin/env python3
"""
HTTP receiver for LifeLens MP4 segments (run on the analysis box, e.g. ASUS on Tailscale).

Endpoints:
  POST /meta   — JSON: { "kind", "segment_index", "byte_length", "content_type" } (optional ping before file)
  POST /segment — raw body: video/mp4; header X-LifeLens-Segment-Index

Bind to 0.0.0.0 so Tailscale can reach the process; use the machine’s tailnet IP from `tailscale ip -4`.

Default save location: ~/Documents/stream_server/received_segments (override with --dir).

Example (ASUS):
  python segment_receiver.py --host 0.0.0.0 --port 8788

Example (Mac relay):
  python relay_server.py --send-segment-meta-url http://100.x.x.x:8788/meta \\
    --send-segment-url http://100.x.x.x:8788/segment
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def _default_receive_dir() -> Path:
    # Use expanduser() so the path is one expression (avoids typos like Path.ho vs Path.home).
    return Path("~/Documents/stream_server/received_segments").expanduser()


class SegmentReceiverHandler(BaseHTTPRequestHandler):
    server_version = "LifeLensSegmentReceiver/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send(self, code: int, body: bytes | None = None, content_type: str = "text/plain; charset=utf-8") -> None:
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
            print(f"[meta] segment_index={idx} byte_length={bl} kind={obj.get('kind')!r}")
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
            except OSError as e:
                print(f"[!] write failed: {e}")
                self._send(500, str(e).encode("utf-8", errors="replace"))
                return
            print(f"[segment] saved {len(raw)} B -> {dest}")
            self._send(200, b"ok\n")
            return

        self._send(404, b"use POST /meta or POST /segment\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Receive LifeLens MP4 segments over HTTP (Tailscale-friendly)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8788)
    p.add_argument(
        "--dir",
        default=str(_default_receive_dir()),
        help="Directory for incoming .mp4 files (default: ~/Documents/stream_server/received_segments)",
    )
    args = p.parse_args()

    out_dir = Path(args.dir).expanduser().resolve()

    httpd = ThreadingHTTPServer((args.host, args.port), SegmentReceiverHandler)
    httpd.lifelens_out_dir = out_dir

    print(f"LifeLens segment receiver  http://{args.host}:{args.port}/")
    print(f"  POST /meta    (JSON)  optional preview of incoming segment")
    print(f"  POST /segment (video/mp4 body)")
    print(f"  Saving files to: {out_dir}/")
    print()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
