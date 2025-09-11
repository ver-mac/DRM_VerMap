# DRM Live Stream Map

A FastAPI + SQLite + Leaflet app to visualize live GPS locations of Digi Remote Manager (DRM) devices on a map.  
It supports:
- Listing connected devices
- Viewing device details and metrics
- Playback of historical location data
- Live updates via Server-Sent Events (SSE)

---

## 📂 Project Structure

```
DRM/
├── frontend/        # Static frontend (Leaflet + JS)
├── db.py            # SQLite helper functions
├── digirm.py        # Digi Remote Manager API client
├── server.py        # FastAPI backend
├── sse.py           # Simple SSE broker
├── telemetry.db     # SQLite database (created at runtime)
├── .env             # Environment variables (not committed)
├── requirements.txt # Python dependencies
└── .gitignore       # Git ignore rules
```

---

## ⚙️ Setup

### 1. Clone the repo
```bash
git clone https://github.com/your-org/drm-live-map.git
cd drm-live-map
```

### 2. Create and activate a virtual environment (recommended)
```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
Copy `.env.example` → `.env` and set your DRM credentials:

```ini
DRM_BASE_URL=https://remotemanager.digi.com
DRM_USERNAME=your-username
DRM_PASSWORD=your-password

# Poll interval (seconds)
POLL_SECONDS=3

# SQLite file path
DB_PATH=telemetry.db

# Allowed frontend origins (for CORS)
CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

---

## ▶️ Run the app

### Development
```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Open: [http://localhost:8000/app/](http://localhost:8000/app/)

---

## 🌍 Share with others

If you want to share the app over the internet, use [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Ngrok will give you a public URL like:
```
https://xxxx-1234.ngrok-free.app
```

Open: `https://xxxx-1234.ngrok-free.app/app/`

---

## 🗄️ Database

- SQLite is used for storing device metadata and location history.
- The database file is `telemetry.db` (ignored by git).
- A new one is created automatically on startup if it doesn’t exist.

---

## 🚀 Features Roadmap
- [x] Device list with details (name, type, FW)
- [x] Playback controls (play, pause, step, speed)
- [x] Live SSE updates
- [ ] Timeline slider improvements
- [ ] Export data (CSV/GeoJSON)
- [ ] Docker image for deployment

