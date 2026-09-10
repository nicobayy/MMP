"""Wallet win-rate tracker (SQLite).
V1 hemat kredit: kandidat = OWNER wallet top holders (di-resolve dari ATA
via getMultipleAccounts, 1 call) per token PASS Solana.
Outcome dicatat via scripts/record_outcome.py (manual dulu, auto nanti).
Trusted = win_rate >= threshold dengan min_trades cukup.
"""
from __future__ import annotations
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets(
  wallet TEXT PRIMARY KEY,
  chain TEXT DEFAULT 'solana',
  label TEXT DEFAULT '',
  wins INTEGER DEFAULT 0,
  losses INTEGER DEFAULT 0,
  total_pnl REAL DEFAULT 0.0,
  first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS wallet_sightings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wallet TEXT, token TEXT, symbol TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(wallet, token)
);
"""

def init(con: sqlite3.Connection):
    con.executescript(SCHEMA)
    con.commit()

def upsert_candidate(con: sqlite3.Connection, wallet: str, chain: str = "solana"):
    con.execute("INSERT OR IGNORE INTO wallets(wallet, chain) VALUES(?, ?)", (wallet, chain))
    con.execute("UPDATE wallets SET last_seen=CURRENT_TIMESTAMP WHERE wallet=?", (wallet,))
    con.commit()

def add_sighting(con: sqlite3.Connection, wallet: str, token: str, symbol: str = ""):
    upsert_candidate(con, wallet)
    con.execute("INSERT OR IGNORE INTO wallet_sightings(wallet, token, symbol) VALUES(?,?,?)", (wallet, token, symbol))
    con.commit()

def record_outcome(con: sqlite3.Connection, wallet: str, win: bool, pnl: float = 0.0):
    upsert_candidate(con, wallet)
    if win:
        con.execute("UPDATE wallets SET wins=wins+1, total_pnl=total_pnl+?, last_seen=CURRENT_TIMESTAMP WHERE wallet=?", (pnl, wallet))
    else:
        con.execute("UPDATE wallets SET losses=losses+1, total_pnl=total_pnl+?, last_seen=CURRENT_TIMESTAMP WHERE wallet=?", (pnl, wallet))
    con.commit()

def stats(con: sqlite3.Connection, wallet: str) -> dict:
    row = con.execute("SELECT wins, losses, total_pnl FROM wallets WHERE wallet=?", (wallet,)).fetchone()
    if not row:
        return {"wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0}
    w, l, p = row
    t = w + l
    return {"wins": w, "losses": l, "win_rate": round(w / t, 3) if t else 0.0, "total_pnl": p}

def trusted(con: sqlite3.Connection, min_trades: int = 5, min_win_rate: float = 0.6) -> list[str]:
    rows = con.execute("SELECT wallet, wins, losses FROM wallets").fetchall()
    out = []
    for w, wins, losses in rows:
        t = (wins or 0) + (losses or 0)
        if t >= min_trades and (wins / t) >= min_win_rate:
            out.append(w)
    return out

def overlap_bonus(holders: list[str], trusted_wallets: list[str], per_wallet: float = 5.0, max_bonus: float = 15.0) -> tuple[float, int]:
    """Bonus SM bila top holders berisi wallet terpercaya. Return (bonus, n_overlap)."""
    if not holders or not trusted_wallets:
        return 0.0, 0
    tset = set(trusted_wallets)
    n = sum(1 for h in holders if h in tset)
    return min(n * per_wallet, max_bonus), n
