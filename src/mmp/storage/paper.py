"""Paper trading storage: buka posisi virtual tiap PASS, settle via harga live.
Tujuan: bukti expectancy sebelum uang asli dipakai.
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_positions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER DEFAULT 0,
  symbol TEXT DEFAULT '', chain TEXT DEFAULT '', token TEXT DEFAULT '', pair_addr TEXT DEFAULT '',
  entry REAL DEFAULT 0, sl REAL DEFAULT 0, tp REAL DEFAULT 0,
  risk_pct REAL DEFAULT 1.0, status TEXT DEFAULT 'OPEN',
  opened_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  closed_ts DATETIME DEFAULT NULL,
  exit_price REAL DEFAULT NULL, pnl_pct REAL DEFAULT NULL, close_reason TEXT DEFAULT ''
);
"""

def init(con: sqlite3.Connection):
    con.execute(SCHEMA)
    try:  # migrasi non-destruktif untuk DB lama
        con.execute("ALTER TABLE paper_positions ADD COLUMN tier INTEGER DEFAULT 1")
    except Exception as e:
        log.debug("paper migrate skip: %s", str(e)[:120])
    try:  # pool Gecko untuk analisis MAE/MFE dari candle cache (token mati hilang dari API)
        con.execute("ALTER TABLE paper_positions ADD COLUMN pool TEXT DEFAULT ''")
    except Exception as e:
        log.debug("paper migrate pool skip: %s", str(e)[:120])
    con.commit()

def open_from_signal(con: sqlite3.Connection, sig: dict, risk_pct: float = 1.0) -> int:
    plan = sig.get("plan") or {}
    cur = con.execute(
        "INSERT INTO paper_positions(signal_id, symbol, chain, token, pair_addr, entry, sl, tp, risk_pct, tier)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (sig.get("db_id", 0), sig.get("symbol", ""), sig.get("chain", ""), sig.get("token_address", ""),
         sig.get("pair_address", ""), sig.get("price_usd", 0), plan.get("stop_loss", 0),
         plan.get("take_profit", 0), risk_pct, int(sig.get("tier") or 1)))
    con.commit()
    rid = cur.lastrowid
    return int(rid) if rid is not None else 0

def list_open(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("SELECT id, signal_id, symbol, chain, token, pair_addr, entry, sl, tp, opened_ts FROM paper_positions WHERE status='OPEN'").fetchall()
    return [{"id": r[0], "signal_id": r[1], "symbol": r[2], "chain": r[3], "token": r[4], "pair_addr": r[5], "entry": r[6], "sl": r[7], "tp": r[8], "opened_ts": r[9]} for r in rows]

def has_open(con: sqlite3.Connection, pair_addr: str) -> bool:
    """Dedup: 1 pair = max 1 posisi OPEN (cegah tumpukan tiap scan)."""
    row = con.execute("SELECT 1 FROM paper_positions WHERE status='OPEN' AND pair_addr=? LIMIT 1", (pair_addr,)).fetchone()
    return row is not None

def recently_closed(con: sqlite3.Connection, chain: str, token: str, pair_addr: str,
                    hours: float = 12.0) -> tuple[bool, str | None]:
    """True bila token yang sama sudah ada posisi CLOSED dalam < hours jam.

    Mencegah re-entry chase: entry pertama TP (+15%), entry kedua di token sama
    15 menit kemudian cenderung masuk di pucuk lalu SL (kasus Stunk/MM:
    #1-#3 TP, #4-#5 SL). Kunci = chain:token (fallback pair).
    """
    if hours is not None and float(hours) <= 0:
        return False, None
    ch = (chain or "").strip()
    tok = (token or "").strip()
    try:
        if tok:
            row = con.execute(
                "SELECT MAX(closed_ts) FROM paper_positions WHERE status='CLOSED'"
                " AND LOWER(chain)=LOWER(?) AND LOWER(token)=LOWER(?)",
                (ch, tok)).fetchone()
        else:
            row = con.execute(
                "SELECT MAX(closed_ts) FROM paper_positions WHERE status='CLOSED'"
                " AND pair_addr=?", (pair_addr,)).fetchone()
        last_ts = str(row[0]) if row and row[0] else None
        if not last_ts:
            return False, None
        from datetime import datetime, timedelta, timezone
        last = datetime.fromisoformat(last_ts)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        dup = datetime.now(timezone.utc) - last < timedelta(hours=float(hours))
        return dup, last_ts
    except Exception as e:
        log.debug("recently_closed skip: %s", str(e)[:120])
        return False, None

def close_position(con: sqlite3.Connection, pid: int, exit_price: float, pnl_pct: float, reason: str):
    con.execute("UPDATE paper_positions SET status='CLOSED', closed_ts=CURRENT_TIMESTAMP,"
                " exit_price=?, pnl_pct=?, close_reason=? WHERE id=?", (exit_price, pnl_pct, reason, pid))
    con.commit()

def set_pool(con: sqlite3.Connection, pid: int, pool: str):
    """Rekam pool Gecko posisi (best-effort, untuk analisis cache pasca-mati)."""
    if not pool:
        return
    try:
        con.execute("UPDATE paper_positions SET pool=? WHERE id=? AND (pool IS NULL OR pool='')",
                    (pool, pid))
        con.commit()
    except Exception as e:
        log.debug("paper set_pool skip: %s", str(e)[:120])
