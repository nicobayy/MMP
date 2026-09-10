"""KOL callout tracker (SQLite).
Alur: catat callout manual via scripts/add_callout.py
(score KOL dihitung dari callout 48 jam terakhir untuk token itu;
 trusted channel berbobot lebih — anti FOMO dari 1 akun random).
"""
from __future__ import annotations
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS kol_callouts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  source TEXT DEFAULT 'telegram',
  handle TEXT DEFAULT '',
  token TEXT DEFAULT '',
  symbol TEXT DEFAULT '',
  chain TEXT DEFAULT 'solana',
  trusted INTEGER DEFAULT 0,
  note TEXT DEFAULT ''
);
"""

def init(con: sqlite3.Connection):
    con.execute(SCHEMA)
    con.commit()

def add_callout(con: sqlite3.Connection, token: str, symbol: str = "", chain: str = "solana",
                source: str = "telegram", handle: str = "", trusted: bool = False, note: str = "") -> int:
    cur = con.execute(
        "INSERT INTO kol_callouts(source, handle, token, symbol, chain, trusted, note)"
        " VALUES(?,?,?,?,?,?,?)",
        (source, handle, token, symbol, chain, 1 if trusted else 0, note))
    con.commit()
    return int(cur.lastrowid)

def recent_for_token(con: sqlite3.Connection, token: str, hours: int = 48) -> list[dict]:
    try:
        rows = con.execute(
            "SELECT source, handle, trusted, ts FROM kol_callouts"
            " WHERE token=? AND ts >= datetime('now', ?)",
            (token, f"-{hours} hours")).fetchall()
    except Exception:
        return []
    return [{"source": r[0], "handle": r[1], "trusted": bool(r[2]), "ts": r[3]} for r in rows]
