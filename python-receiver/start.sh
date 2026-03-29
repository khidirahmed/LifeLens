#!/bin/bash
# LifeLens – start receiver + ngrok tunnel
# Usage: ./start.sh [your-ngrok-authtoken]
#
# Get a free authtoken at https://dashboard.ngrok.com/authtokens

set -e

NGROK_TOKEN="${1:-$NGROK_AUTHTOKEN}"

# ── deps ──────────────────────────────────────────────────────────────────────
echo "[*] Checking dependencies..."
pip3 install -q websockets opencv-python numpy pyngrok

# ── ngrok auth ────────────────────────────────────────────────────────────────
if [ -n "$NGROK_TOKEN" ]; then
    python3 -c "from pyngrok import ngrok; ngrok.set_auth_token('$NGROK_TOKEN')"
    echo "[*] ngrok auth token set."
fi

# ── start ─────────────────────────────────────────────────────────────────────
echo "[*] Starting LifeLens receiver with tunnel..."
python3 - <<'PYEOF'
import asyncio
import threading
import sys
import signal
import numpy as np
import cv2
import websockets

try:
    from pyngrok import ngrok, conf
    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False

HOST = "0.0.0.0"
PORT = 8765

latest_frame = None
frame_count = 0
connected_clients = set()

async def handle_client(websocket):
    global latest_frame, frame_count
    client_addr = websocket.remote_address
    connected_clients.add(websocket)
    print(f"[+] iOS app connected from {client_addr}")
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                np_arr = np.frombuffer(message, dtype=np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    latest_frame = frame
                    frame_count += 1
            else:
                print(f"[i] Text: {message}")
    except websockets.exceptions.ConnectionClosed:
        print(f"[-] Disconnected: {client_addr}")
    finally:
        connected_clients.discard(websocket)

async def start_server():
    async with websockets.serve(handle_client, HOST, PORT):
        await asyncio.Future()

def display_loop(ws_url):
    global latest_frame, frame_count
    print(f"\n{'='*54}")
    print("  LifeLens Receiver")
    print(f"{'='*54}")
    print(f"  Local : ws://0.0.0.0:{PORT}")
    if ws_url:
        print(f"  Tunnel: {ws_url}")
        print()
        print("  ► Enter this in the LifeLens app:")
        host = ws_url.replace("tcp://", "").replace("ws://", "").split(":")[0]
        port = ws_url.split(":")[-1] if ":" in ws_url.replace("tcp://","") else PORT
        print(f"    Host: {host}")
        print(f"    Port: {port}")
    else:
        import subprocess
        local_ip = subprocess.check_output(
            ["ipconfig", "getifaddr", "en0"], text=True
        ).strip()
        print(f"  ► No tunnel. Use local IP (same Wi-Fi only):")
        print(f"    Host: {local_ip}  Port: {PORT}")
    print(f"{'='*54}")
    print("  Press 'q' to quit, 's' to save screenshot\n")

    cv2.namedWindow("LifeLens Stream", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("LifeLens Stream", 1280, 720)
    while True:
        if latest_frame is not None:
            display = latest_frame.copy()
            cv2.putText(display, f"Frames: {frame_count}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            if connected_clients:
                cv2.putText(display, "LIVE", (display.shape[1] - 80, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow("LifeLens Stream", display)
        else:
            placeholder = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(placeholder, "Waiting for stream...", (420, 350),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)
            cv2.imshow("LifeLens Stream", placeholder)

        key = cv2.waitKey(16) & 0xFF
        if key == ord("q"):
            print("\n[*] Shutting down...")
            break
        elif key == ord("s") and latest_frame is not None:
            filename = f"lifelens_screenshot_{frame_count}.jpg"
            cv2.imwrite(filename, latest_frame)
            print(f"[+] Screenshot saved: {filename}")

    cv2.destroyAllWindows()

def main():
    ws_url = None

    if NGROK_AVAILABLE:
        try:
            tunnel = ngrok.connect(PORT, "tcp")
            ws_url = tunnel.public_url
        except Exception as e:
            print(f"[!] ngrok tunnel failed: {e}")
            print("    Run:  ./start.sh <your-ngrok-authtoken>")
            print("    Get one free at https://dashboard.ngrok.com/authtokens\n")

    loop = asyncio.new_event_loop()
    server_thread = threading.Thread(
        target=lambda: loop.run_until_complete(start_server()),
        daemon=True,
    )
    server_thread.start()

    try:
        display_loop(ws_url)
    except KeyboardInterrupt:
        print("\n[*] Interrupted")
    finally:
        if NGROK_AVAILABLE and ws_url:
            ngrok.disconnect(ws_url)
        loop.call_soon_threadsafe(loop.stop)
        sys.exit(0)

main()
PYEOF
