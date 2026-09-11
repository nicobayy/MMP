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
    if path == ":memory:":
        con = sqlite3.connect(path)
    else:
        # Maka: scheduler (multi-proses) + scan paralel (multi-thread) berbagi DB.
        con = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    try:
        con.execute("PRAGMA journal_mode=WAL")  # baca tak blokir tulis
        con.execute("PRAGMA synchronous=NORMAL")  # aman dgn WAL, fsync tiap commit tetap
        con.execute("PRAGMA busy_timeout=5000")  # scheduler + manual berbagi DB
    except Exception as e:
        log.debug("pragma skip: %s", str(e)[:120])
    con.executescript(SCHEMA)
    return con

_SAVE_RETRY = 3


def save(con, sig) -> int:
    d = sig.to_dict()
    args = (d["verdict"], d["symbol"], d["chain"], d["token_address"], d["pair_address"],
            d["price_usd"], d["confidence"], d["reason"], json.dumps(d, default=str))
    last: Exception | None = None
    for attempt in range(_SAVE_RETRY):
        try:
            cur = con.execute(
                "INSERT INTO signals(verdict,symbol,chain,token,pair_addr,price,confidence,reason,payload)"
                " VALUES(?,?,?,?,?,?,?,?,?)", args)
            con.commit()
            return int(cur.lastrowid)
        except sqlite3.OperationalError as e:
            last = e  # database is locked -> retry singkat
            try:
                import time as _t
                _t.sleep(0.2 * (attempt + 1))
            except Exception:
                pass
    log.warning("signals save gagal setelah retry: %s", str(last)[:160])
    raise last  # type: ignore[misc]

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

def dedup_key(chain: str, token: str, pair_addr: str) -> str:
    """Kunci dedup utama = chain:token (lower). Fallback ke pair bila token kosong/?.

    Alasan: token yang sama bisa punya banyak pair (SOL/USDC, PumpSwap->Raydium
    migrasi). Dedup by pairAddress saja = sinyal ganda untuk token yang sama
    seperti Stocklana di CSV (pair sama di-scan tiap jam).
    """
    ch = (chain or "").strip().lower()
    tok = (token or "").strip()
    if tok and tok != "?":
        return f"{ch}:{tok.lower()}"
    return f"{ch}:pair:{(pair_addr or '').strip().lower()}"

def last_token_signal_ts(con, chain: str, token: str, pair_addr: str) -> str | None:
    """Ambil ts sinyal terakhir untuk token yang sama (atau pair fallback)."""
    ch = (chain or "").strip()
    tok = (token or "").strip()
    try:
        if tok and tok != "?":
            row = con.execute(
                "SELECT MAX(ts) FROM signals WHERE LOWER(chain)=LOWER(?) AND LOWER(token)=LOWER(?)",
                (ch, tok)).fetchone()
        else:
            row = con.execute(
                "SELECT MAX(ts) FROM signals WHERE pair_addr=?",
                (pair_addr,)).fetchone()
        return str(row[0]) if row and row[0] else None
    except Exception as e:
        log.debug("last_token_signal_ts skip: %s", str(e)[:120])
        return None

def is_recent_duplicate(con, chain: str, token: str, pair_addr: str,
                        cooldown_min: int = 120) -> tuple[bool, str | None]:
    """True bila token yang sama sudah disimpan dalam < cooldown_min menit.

    Dipakai untuk skip scan ulang antar-run (scheduler tiap 60m + boosts yang
    itu-itu saja = CSV penuh duplikat Stocklana/POLLY tiap jam).
    """
    last_ts = last_token_signal_ts(con, chain, token, pair_addr)
    if not last_ts:
        return False, None
    try:
        from datetime import datetime, timedelta, timezone
        last = datetime.fromisoformat(str(last_ts))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        dup = datetime.now(timezone.utc) - last < timedelta(minutes=cooldown_min)
        return dup, last_ts
    except Exception as e:
        log.debug("is_recent_duplicate parse skip: %s", str(e)[:120])
        return False, last_ts

def mark_alerted(con, pair_addr: str):
    con.execute("INSERT OR REPLACE INTO sent_alerts(pair_addr, last_sent) VALUES(?, CURRENT_TIMESTAMP)", (pair_addr,))
    con.commit()
