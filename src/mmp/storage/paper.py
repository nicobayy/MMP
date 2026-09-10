"""Paper trading storage: buka posisi virtual tiap PASS, settle via harga live.
Tujuan: bukti expectancy sebelum uang asli dipakai.
"""
from __future__ import annotations

import sqlite3

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
    except Exception:
        pass
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
    rows = con.execute("SELECT id, symbol, chain, token, pair_addr, entry, sl, tp, opened_ts FROM paper_positions WHERE status='OPEN'").fetchall()
    return [{"id": r[0], "symbol": r[1], "chain": r[2], "token": r[3], "pair_addr": r[4], "entry": r[5], "sl": r[6], "tp": r[7], "opened_ts": r[8]} for r in rows]

def has_open(con: sqlite3.Connection, pair_addr: str) -> bool:
    """Dedup: 1 pair = max 1 posisi OPEN (cegah tumpukan tiap scan)."""
    row = con.execute("SELECT 1 FROM paper_positions WHERE status='OPEN' AND pair_addr=? LIMIT 1", (pair_addr,)).fetchone()
    return row is not None

def close_position(con: sqlite3.Connection, pid: int, exit_price: float, pnl_pct: float, reason: str):
    con.execute("UPDATE paper_positions SET status='CLOSED', closed_ts=CURRENT_TIMESTAMP,"
                " exit_price=?, pnl_pct=?, close_reason=? WHERE id=?", (exit_price, pnl_pct, reason, pid))
    con.commit()
