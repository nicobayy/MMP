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

def recent_handles_count(con: sqlite3.Connection, token: str, hours: int = 6) -> int:
    """Jumlah handle BERBEDA yang callout token dalam window pendek.
    Tinggi = indikasi coordinated shilling (atau hype legit — interpretasi di analyzer).
    """
    try:
        row = con.execute(
            "SELECT COUNT(DISTINCT handle) FROM kol_callouts"
            " WHERE token=? AND handle<>'' AND ts >= datetime('now', ?)",
            (token, f"-{hours} hours")).fetchone()
        return int(row[0])
    except Exception:
        return 0

def handle_stats(con: sqlite3.Connection, handle: str) -> dict:
    """Win-rate handle dari outcome paper token yang pernah di-callout.
    TP=win, SL=loss, TIMEOUT ikut apa adanya. Tanpa data -> netral, bukan vonis.
    """
    try:
        rows = con.execute(
            "SELECT DISTINCT token FROM kol_callouts WHERE handle=?", (handle,)).fetchall()
    except Exception:
        return {"calls": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "proven": False}
    tokens = [r[0] for r in rows if r[0]]
    if not tokens:
        return {"calls": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "proven": False}
    q = ",".join("?" for _ in tokens)
    try:
        outs = con.execute(
            f"SELECT close_reason FROM paper_positions WHERE status='CLOSED' AND token IN ({q})", tokens).fetchall()
    except Exception:
        outs = []
    wins = sum(1 for o in outs if o[0] == "TP")
    losses = sum(1 for o in outs if o[0] in ("SL", "TIMEOUT"))
    n = wins + losses
    wr = round(wins / n, 3) if n else 0.0
    return {"calls": len(tokens), "wins": wins, "losses": losses, "win_rate": wr,
            "proven": bool(n >= 3 and wr >= 0.6)}
