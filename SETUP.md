# LifeLens — Setup Guide

## Project Structure

```
LifeLens/
├── Backend/
│   ├── main.py            ← FastAPI server
│   └── requirements.txt
└── iOS/
    └── LifeLens/
        ├── LifeLensApp.swift
        ├── ContentView.swift
        ├── Info.plist            ← add to your Xcode project
        ├── Views/
        │   ├── LoginView.swift
        │   ├── HomeView.swift
        │   └── VideoUploadView.swift
        ├── ViewModels/
        │   ├── AuthViewModel.swift
        │   └── VideoUploadViewModel.swift
        ├── Services/
        │   └── APIService.swift
        └── Models/
            └── UploadResult.swift
```

---

## 1. Run the FastAPI Backend

```bash
cd Backend

# Create a virtual environment (one-time)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be live at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### Hex API Keys
Set your Hex credentials as environment variables before starting:
```bash
export HEX_API_KEY="your-real-hex-api-key"
export HEX_BASE_URL="https://your-hex-endpoint.hex.tech"   # update to actual URL
export HEX_BUCKET="lifelens-videos"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Default test accounts
| Username | Password     |
|----------|--------------|
| admin    | password123  |
| david    | lifelens123  |

---

## 2. Set Up the iOS Xcode Project

1. **Create a new Xcode project**
   - Open Xcode → New Project → iOS → App
   - Product Name: `LifeLens`
   - Interface: SwiftUI, Language: Swift
   - Minimum Deployment: iOS 16.0

2. **Add all Swift files**
   - Drag the entire `iOS/LifeLens/` folder into your Xcode project
   - Make sure "Copy items if needed" is checked

3. **Update Info.plist**
   - Open your project's Info.plist in Xcode
   - Add the two keys from `iOS/LifeLens/Info.plist`:
     - `NSPhotoLibraryUsageDescription` (required for video picker)
     - `NSAppTransportSecurity` → `NSAllowsLocalNetworking: YES` (for local HTTP)

4. **Set your server IP** (for real iPhone testing)
   - Open `Services/APIService.swift`
   - Change `kBaseURL` from `http://localhost:8000` to your Mac's local IP:
     ```swift
     private let kBaseURL = "http://192.168.1.42:8000"   // ← your Mac's IP
     ```
   - Find your Mac's IP: `System Settings → Wi-Fi → Details` or run `ifconfig | grep "inet "`
   - Your iPhone and Mac must be on the same Wi-Fi network

5. **Build & Run** on your iPhone (or Simulator)

---

## 3. How It Works

```
iPhone (SwiftUI App)
  │
  │  POST /auth/login  →  Bearer token
  │  POST /upload/video (multipart, token in header)
  ▼
FastAPI Server (your Mac)
  │  Saves video locally (uploads/ folder)
  │  Uploads to Hex cloud storage
  │  [Future] Sends frames to LLM for safety analysis
  ▼
Hex Storage  ←→  LLM Analysis (coming next)
```

---

## 4. API Endpoints

| Method | Path            | Auth?  | Description                    |
|--------|-----------------|--------|--------------------------------|
| GET    | /health         | No     | Server health check            |
| POST   | /auth/login     | No     | Get Bearer token               |
| POST   | /upload/video   | Yes    | Upload video for analysis      |

---

## 5. Next Steps

- [ ] Connect real Hex API endpoint (update `HEX_BASE_URL` in `main.py`)
- [ ] Integrate vision LLM in `analyze_video()` function in `main.py`
- [ ] Add push notifications (alert family members on hazard detection)
- [ ] Replace in-memory auth with a real database + JWT tokens
- [ ] Add 40-second video clip processing logic
