"""SQLite storage untuk audit + hitung precision ke depan."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  verdict TEXT, symbol TEXT, chain TEXT, token TEXT, pair_addr TEXT,
  price REAL, confidence REAL, reason TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS sent_alerts(
  pair_addr TEXT PRIMARY KEY,
  last_sent DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def connect(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA busy_timeout=5000")  # scheduler + manual berbagi DB
    except Exception as e:
        log.debug("pragma busy_timeout skip: %s", str(e)[:120])
    con.executescript(SCHEMA)
    return con

def save(con, sig) -> int:
    d = sig.to_dict()
    cur = con.execute(
        "INSERT INTO signals(verdict,symbol,chain,token,pair_addr,price,confidence,reason,payload)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (d["verdict"], d["symbol"], d["chain"], d["token_address"], d["pair_address"],
         d["price_usd"], d["confidence"], d["reason"], json.dumps(d, default=str)))
    con.commit()
    return int(cur.lastrowid)

def should_alert(con, pair_addr: str, cooldown_min: int = 120) -> bool:
    row = con.execute("SELECT last_sent FROM sent_alerts WHERE pair_addr=?", (pair_addr,)).fetchone()
    if not row:
        return True
    try:
        from datetime import datetime, timedelta, timezone
        # SQLite CURRENT_TIMESTAMP = UTC; bandingkan dengan UTC agar tak salah zona.
        last = datetime.fromisoformat(str(row[0]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last > timedelta(minutes=cooldown_min)
    except Exception as e:
        log.debug("should_alert parse skip: %s", str(e)[:120])
        return True

def mark_alerted(con, pair_addr: str):
    con.execute("INSERT OR REPLACE INTO sent_alerts(pair_addr, last_sent) VALUES(?, CURRENT_TIMESTAMP)", (pair_addr,))
    con.commit()
