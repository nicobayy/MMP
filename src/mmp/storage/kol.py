"""KOL callout tracker (SQLite).
Alur: catat callout manual via scripts/add_callout.py
(score KOL dihitung dari callout 48 jam terakhir untuk token itu;
 trusted channel berbobot lebih — anti FOMO dari 1 akun random).
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

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
    for col in ("trust TEXT DEFAULT 'untrusted'", "reason TEXT DEFAULT ''"):
        try:
            con.execute(f"ALTER TABLE kol_callouts ADD COLUMN {col}")
        except Exception as e:
            log.debug("kol migrate skip: %s", str(e)[:120])
    con.commit()

TRUST_LEVELS = ("trusted", "trial", "untrusted")
REASONS = ("launch", "listing", "whale_buy", "rotation", "narrative", "other")

def _trust_of(row_trust: str, legacy_trusted: int) -> str:
    if row_trust in TRUST_LEVELS:
        return row_trust
    return "trusted" if legacy_trusted else "untrusted"

def add_callout(con: sqlite3.Connection, token: str, symbol: str = "", chain: str = "solana",
                source: str = "telegram", handle: str = "", trusted: bool = False, note: str = "",
                trust: str = "", reason: str = "") -> int:
    trust = trust if trust in TRUST_LEVELS else ("trusted" if trusted else "untrusted")
    reason = reason if reason in REASONS else ("other" if reason else "")
    cur = con.execute(
        "INSERT INTO kol_callouts(source, handle, token, symbol, chain, trusted, note, trust, reason)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (source, handle, token, symbol, chain, 1 if trust == "trusted" else 0, note, trust, reason))
    con.commit()
    rid = cur.lastrowid
    return int(rid) if rid is not None else 0

def recent_for_token(con: sqlite3.Connection, token: str, hours: int = 48) -> list[dict]:
    """Butuh init() dulu (migrasi kolom trust/reason)."""
    try:
        rows = con.execute(
            "SELECT source, handle, trusted, ts, trust, reason FROM kol_callouts"
            " WHERE token=? AND ts >= datetime('now', ?)",
            (token, f"-{hours} hours")).fetchall()
    except Exception as e:
        log.debug("kol recent skip: %s", str(e)[:120])
        return []
    out = []
    for r in rows:
        trust = _trust_of(r[4] or "", r[2])
        out.append({"source": r[0], "handle": r[1], "trusted": trust == "trusted",
                    "trust": trust, "reason": r[5] or "", "ts": r[3]})
    return out

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
    except Exception as e:
        log.debug("kol handles count skip: %s", str(e)[:120])
        return 0

def handle_stats(con: sqlite3.Connection, handle: str) -> dict:
    """Win-rate handle dari outcome paper token yang pernah di-callout.
    TP=win, SL=loss, TIMEOUT ikut apa adanya. Tanpa data -> netral, bukan vonis.
    """
    try:
        rows = con.execute(
            "SELECT DISTINCT token FROM kol_callouts WHERE handle=?", (handle,)).fetchall()
    except Exception as e:
        log.debug("kol handle tokens skip: %s", str(e)[:120])
        return {"calls": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "proven": False}
    tokens = [r[0] for r in rows if r[0]]
    if not tokens:
        return {"calls": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "proven": False}
    q = ",".join("?" for _ in tokens)
    try:
        outs = con.execute(
            f"SELECT close_reason FROM paper_positions WHERE status='CLOSED' AND token IN ({q})", tokens).fetchall()
    except Exception as e:
        log.debug("kol handle outcomes skip: %s", str(e)[:120])
        outs = []
    wins = sum(1 for o in outs if o[0] == "TP")
    losses = sum(1 for o in outs if o[0] in ("SL", "TIMEOUT"))
    n = wins + losses
    wr = round(wins / n, 3) if n else 0.0
    return {"calls": len(tokens), "wins": wins, "losses": losses, "win_rate": wr,
            "proven": bool(n >= 3 and wr >= 0.6)}

TRUST_CEIL = {"trusted": 1.5, "trial": 1.0, "untrusted": 0.5}

def handle_weight(con: sqlite3.Connection, handle: str, trust: str = "trusted") -> tuple[float, str]:
    """Bobot reputasi handle: DIBAYAR track record, bukan popularitas.
    - outcome: proven (n>=3, wr>=0.6) 1.5 / baru (n<3) 0.5 / normal 1.0 /
      gagal (n>=3, wr<0.4) 0.0 + downranked (diabaikan total).
    - plafon tier input: trusted 1.5 / trial 1.0 / untrusted 0.5.
    Return (bobot, label). Precision (win_rate) vs volume (calls) terpisah di stats.
    """
    st = handle_stats(con, handle)
    n = st["wins"] + st["losses"]
    if n == 0:
        base, why = 0.5, "baru (belum ada outcome)"
    elif n >= 3 and st["win_rate"] >= 0.6:
        base, why = 1.5, f"proven {st['win_rate']:.0%} dari {n}"
    elif n >= 3 and st["win_rate"] < 0.4:
        return 0.0, f"downranked {st['win_rate']:.0%} dari {n} (diabaikan)"
    else:
        base, why = 1.0, f"trial {st['win_rate']:.0%} dari {n}"
    cap = TRUST_CEIL.get(trust, 0.5)
    w = min(base, cap)
    if w < base:
        why += f" + plafon {trust} {cap}"
    return round(w, 2), why
