import os
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "telemetry.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS devices (
  id   TEXT PRIMARY KEY,
  name TEXT,
  type TEXT,
  fw   TEXT
);

CREATE TABLE IF NOT EXISTS locations (
  device_id TEXT NOT NULL,
  ts        TEXT NOT NULL,   -- ISO8601 string from DRM (UTC)
  lat       REAL NOT NULL,
  lon       REAL NOT NULL,
  accuracy  REAL,
  source    TEXT,
  PRIMARY KEY (device_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_locations_ts ON locations(ts);
CREATE INDEX IF NOT EXISTS idx_locations_device_ts ON locations(device_id, ts DESC);
"""

async def open_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA synchronous=NORMAL;")
    return db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()

async def upsert_devices(rows):
    """
    rows: list of dicts with keys id, name, type, fw
    """
    if not rows:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO devices(id, name, type, fw) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, type=excluded.type, fw=excluded.fw",
            [(r["id"], r.get("name"), r.get("type"), r.get("fw")) for r in rows]
        )
        await db.commit()

async def insert_locations(rows):
    """
    rows: list of tuples (device_id, ts, lat, lon, accuracy, source)
    Uses INSERT OR IGNORE to avoid duplicates.
    """
    if not rows:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO locations(device_id, ts, lat, lon, accuracy, source) "
            "VALUES (?,?,?,?,?,?)",
            rows
        )
        await db.commit()
        return db.total_changes

async def last_ts_for_device(device_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ts FROM locations WHERE device_id=? ORDER BY ts DESC LIMIT 1", (device_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def query_history(device_id: str, start: str = None, end: str = None, limit: int = 1000, asc=True):
    sql = "SELECT ts, lat, lon FROM locations WHERE device_id=?"
    params = [device_id]
    if start:
        sql += " AND ts >= ?"; params.append(start)
    if end:
        sql += " AND ts <= ?"; params.append(end)
    sql += " ORDER BY ts " + ("ASC" if asc else "DESC")
    sql += " LIMIT ?"; params.append(limit)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            # Return oldest→newest by default
            return [{"ts": r[0], "lat": r[1], "lon": r[2]} for r in rows]
