import asyncio
import signal
import sys
import numpy as np
import cv2
import websockets

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
                    print("[!] Failed to decode frame")
            else:
                print(f"[i] Text message: {message}")
    except websockets.exceptions.ConnectionClosed:
        print(f"[-] iOS app disconnected: {client_addr}")
    finally:
        connected_clients.discard(websocket)

def display_loop():
    global latest_frame, frame_count
    print(f"\n{'='*50}")
    print("Ray-Ban Meta Stream Receiver")
    print(f"{'='*50}")
    print(f"Listening on ws://{HOST}:{PORT}")
    print("Waiting for iOS app to connect...")
    print("Press 'q' to quit, 's' to save a screenshot")
    print(f"{'='*50}\n")
    cv2.namedWindow("Ray-Ban Meta Stream", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Ray-Ban Meta Stream", 1280, 720)
    while True:
        if latest_frame is not None:
            display = latest_frame.copy()
            cv2.putText(display, f"Frames: {frame_count}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            if connected_clients:
                cv2.putText(display, "LIVE", (display.shape[1] - 80, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow("Ray-Ban Meta Stream", display)
        else:
            placeholder = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(placeholder, "Waiting for stream...", (420, 350),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)
            cv2.putText(placeholder, f"ws://{HOST}:{PORT}", (460, 400),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 80, 80), 1)
            cv2.imshow("Ray-Ban Meta Stream", placeholder)
        key = cv2.waitKey(16) & 0xFF
        if key == ord("q"):
            print("\n[*] Shutting down...")
            break
        elif key == ord("s") and latest_frame is not None:
            filename = f"rayban_screenshot_{frame_count}.jpg"
            cv2.imwrite(filename, latest_frame)
            print(f"[+] Screenshot saved: {filename}")
    cv2.destroyAllWindows()

async def start_server():
    async with websockets.serve(handle_client, HOST, PORT):
        await asyncio.Future()

def main():
    loop = asyncio.new_event_loop()
    import threading
    server_thread = threading.Thread(
        target=lambda: loop.run_until_complete(start_server()),
        daemon=True,
    )
    server_thread.start()
    try:
        display_loop()
    except KeyboardInterrupt:
        print("\n[*] Interrupted")
    finally:
        loop.call_soon_threadsafe(loop.stop)
        sys.exit(0)

if __name__ == "__main__":
    main()
