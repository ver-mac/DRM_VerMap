import os
from pathlib import Path

from dotenv import load_dotenv
# Load .env that sits in the same folder as this file
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

import json
import asyncio
from typing import Dict, Optional, Tuple
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# IMPORTANT: only import modules that read env AFTER load_dotenv
from db import (
    init_db,
    upsert_devices,
    insert_locations,
    last_ts_for_device,
    query_history,
    list_devices,
)
from digirm import device_rows_for_db, fetch_stream_history, fetch_stream_latest, parse_latlon
from sse import broker

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "3"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app = FastAPI(title="DRM Live Map with SQLite")
app.mount("/app", StaticFiles(directory="frontend", html=True), name="app")

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ---- background poller manager ----

class PollerManager:
    """
    Keeps one polling task per device_id.
    Each task:
      - calls streams/history with start_time = last seen
      - inserts new rows into SQLite
      - publishes new rows to SSE broker
    """
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.last_seen_ts: Dict[str, Optional[str]] = {}
        self.lock = asyncio.Lock()

    async def ensure_poller(self, device_id: str, stream: str):
        key = (device_id, stream)
        async with self.lock:
            if key not in self.tasks or self.tasks[key].done():
                t = asyncio.create_task(self._poll_device(device_id, stream))
                self.tasks[key] = t

    async def _poll_device(self, device_id: str, stream: str):
        key = (device_id, stream)
        if key not in self.last_seen_ts:
            # Reuse last_ts if you used a different stream before? We keep per (device,stream)
            self.last_seen_ts[key] = await last_ts_for_device(device_id)

        while True:
            try:
                hist = await fetch_stream_history(device_id, stream=stream, start_time=self.last_seen_ts.get(key))
                new_rows = []
                for p in hist.get("list", []):
                    ts = p.get("timestamp")
                    val = p.get("value")
                    parsed = parse_latlon(val)
                    if not (ts and parsed):
                        continue
                    lat, lon = parsed
                    new_rows.append((device_id, ts, lat, lon, None, f"stream:{stream}"))
                if new_rows:
                    await insert_locations(new_rows)
                    self.last_seen_ts[key] = new_rows[-1][1]
                    for _, ts, lat, lon, _, _ in new_rows:
                        await broker.publish(f"{device_id}:{stream}", {"device_id": device_id, "ts": ts, "lat": lat, "lon": lon})
            except Exception:
                await asyncio.sleep(max(POLL_SECONDS, 5))
            await asyncio.sleep(POLL_SECONDS)


pollers = PollerManager()

# ---- app lifecycle ----

@app.on_event("startup")
async def on_startup():
    await init_db()
    # Optional: prime devices table with all devices
    rows = await device_rows_for_db(only_connected=False)
    await upsert_devices(rows)

# ---- routes ----

@app.get("/api/devices")
async def api_devices(limit: int = 1000):
    rows = await list_devices(limit=limit)
    return {"count": len(rows), "devices": rows}

@app.get("/api/history")
async def api_history(device_id: str, start: str | None = None, end: str | None = None, limit: int = 1000, asc: bool = True):
    if not device_id:
        raise HTTPException(400, "device_id is required")
    
    data = await query_history(device_id, start=start, end=end, limit=limit, asc=asc)
    # If no records were found, attempt a one-shot fetch from DRM and persist
    if start and not data:
        try:
            hist = await fetch_stream_history(device_id, stream="location", start_time=start, size=limit)
            new_rows = []
            for p in hist.get("list", []):
                ts = p.get("timestamp")
                val = p.get("value")
                parsed = parse_latlon(val)
                if ts and parsed:
                    lat, lon = parsed
                    new_rows.append((device_id, ts, lat, lon, None, "stream:location"))
            if new_rows:
                await insert_locations(new_rows)
                data = await query_history(device_id, start=start, end=end, limit=limit, asc=asc)
        except Exception:
            pass

    return {"count": len(data), "list": data}

@app.get("/api/location/latest")
async def api_location_latest(device_id: str = Query(...), stream: str = Query("location")):
    latest = await fetch_stream_latest(device_id, stream=stream)
    if not latest:
        raise HTTPException(404, "Stream not found or no datapoints")
    coords = parse_latlon(latest.get("value"))
    if not coords:
        raise HTTPException(422, "Could not parse lat/lon from latest value")
    lat, lon = coords
    ts = latest.get("timestamp")
    await insert_locations([(device_id, ts, lat, lon, None, f"stream:{stream}")])
    return {"device_id": device_id, "stream": stream, "ts": ts, "lat": lat, "lon": lon}

@app.get("/api/stream/location/{device_id}")
async def sse_location(request: Request, device_id: str, stream: str = "location"):
    # Start/ensure the poller for this stream
    await pollers.ensure_poller(device_id, stream)

    async def event_gen():
        channel = f"{device_id}:{stream}"
        q = await broker.subscribe(channel)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=60.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ":\n\n"   # keep-alive
        finally:
            await broker.unsubscribe(channel, q)

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(event_gen(), headers=headers)