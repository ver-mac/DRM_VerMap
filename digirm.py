import os
import httpx
from typing import Dict, Any, List, Optional, Tuple

DRM_BASE = os.getenv("DRM_BASE_URL", "https://remotemanager.digi.com")
DRM_USER = os.getenv("DRM_USERNAME")
DRM_PASS = os.getenv("DRM_PASSWORD")

def auth_tuple():
    if not (DRM_USER and DRM_PASS):
        raise RuntimeError("Set DRM_USERNAME and DRM_PASSWORD")
    return (DRM_USER, DRM_PASS)

def parse_latlon(val) -> Optional[Tuple[float, float]]:
    # dict: {lat,lon}/{latitude,longitude}/{lat,lng}
    if isinstance(val, dict):
        lat = val.get("lat") or val.get("latitude")
        lon = val.get("lon") or val.get("lng") or val.get("longitude")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except Exception:
                return None
    # JSON string or "lat,lon"
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("{"):
            try:
                import json
                return parse_latlon(json.loads(s))
            except Exception:
                pass
        if "," in s:
            try:
                a, b = s.split(",", 1)
                return float(a.strip()), float(b.strip())
            except Exception:
                return None
    return None

async def list_devices(only_connected=True, size=1000) -> Dict[str, Any]:
    params = {"size": size}
    if only_connected:
        params["query"] = "connection_status='connected'"
    async with httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"}) as client:
        r = await client.get(f"{DRM_BASE}/ws/v1/devices/inventory", params=params, auth=auth_tuple())
        r.raise_for_status()
        return r.json()

async def device_rows_for_db(only_connected=True, size=1000) -> List[dict]:
    inv = await list_devices(only_connected=only_connected, size=size)
    rows = []
    for d in inv.get("list", []):
        rows.append({
            "id": d.get("id"),
            "name": d.get("name") or d.get("id"),
            "type": d.get("type"),
            "fw": d.get("firmware_version"),
        })
    return rows

async def fetch_stream_latest(device_id: str, stream: str = "location") -> Optional[Dict[str, Any]]:
    url = f"{DRM_BASE}/ws/v1/streams/inventory/{device_id}/{stream}"
    async with httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"}) as client:
        r = await client.get(url, auth=auth_tuple())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

async def fetch_stream_history(device_id: str, stream: str = "location",
                               start_time: Optional[str] = None, size: int = 1000) -> Dict[str, Any]:
    params = {"size": size}
    if start_time:
        params["start_time"] = start_time
    url = f"{DRM_BASE}/ws/v1/streams/history/{device_id}/{stream}"
    async with httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"}) as client:
        r = await client.get(url, params=params, auth=auth_tuple())
        if r.status_code == 404:
            return {"count": 0, "list": []}
        r.raise_for_status()
        return r.json()