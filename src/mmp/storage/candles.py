"""Storage candle OHLCV (SQLite) untuk replay & kalibrasi.
Sumber: GeckoTerminal via collectors/ohlcv.py. Upsert per (chain, pool, tf, ts).
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles(
  chain TEXT, pool TEXT, tf TEXT, ts INTEGER,
  o REAL, h REAL, l REAL, c REAL, v REAL,
  PRIMARY KEY (chain, pool, tf, ts)
);
"""

def init(con: sqlite3.Connection):
    con.execute(SCHEMA)
    con.commit()

def upsert_candles(con: sqlite3.Connection, chain: str, pool: str, tf: str, rows: list[dict]) -> int:
    n = 0
    for r in rows:
        try:
            con.execute("INSERT OR REPLACE INTO candles(chain, pool, tf, ts, o, h, l, c, v)"
                        " VALUES(?,?,?,?,?,?,?,?,?)",
                        (chain, pool, tf, int(r["ts"]), float(r["o"]), float(r["h"]),
                         float(r["l"]), float(r["c"]), float(r["v"])))
            n += 1
        except (KeyError, TypeError, ValueError):
            continue
    con.commit()
    return n

def get_candles(con: sqlite3.Connection, chain: str, pool: str, tf: str = "hour",
                since: int = 0, limit: int = 1000) -> list[dict]:
    try:
        rows = con.execute("SELECT ts, o, h, l, c, v FROM candles"
                           " WHERE chain=? AND pool=? AND tf=? AND ts>=?"
                           " ORDER BY ts ASC LIMIT ?",
                           (chain, pool, tf, int(since), int(limit))).fetchall()
    except Exception:
        return []
    return [{"ts": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]} for r in rows]

def coverage(con: sqlite3.Connection) -> list[dict]:
    try:
        rows = con.execute("SELECT chain, pool, tf, COUNT(*), MIN(ts), MAX(ts) FROM candles"
                           " GROUP BY chain, pool, tf").fetchall()
    except Exception:
        return []
    return [{"chain": r[0], "pool": r[1], "tf": r[2], "n": r[3], "oldest": r[4], "newest": r[5]} for r in rows]
