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

def attribute_token_outcome(con: sqlite3.Connection, token: str, win: bool, pnl: float = 0.0) -> int:
    """Tautkan hasil posisi ke SEMUA wallet yang tersight di token itu.
    Dipanggil otomatis tiap paper close — win-rate wallet terbentuk sendiri,
    simetris dengan KOL handle_stats. win = pnl bersih > 0 (konsisten dgn backtest).
    Return jumlah wallet yang dicatat.
    """
    try:
        rows = con.execute("SELECT DISTINCT wallet FROM wallet_sightings WHERE token=?", (token,)).fetchall()
    except Exception:
        return 0
    n = 0
    for (w,) in rows:
        try:
            record_outcome(con, w, win, pnl)
            n += 1
        except Exception:
            continue
    return n

def stats(con: sqlite3.Connection, wallet: str) -> dict:
    row = con.execute("SELECT wins, losses, total_pnl FROM wallets WHERE wallet=?", (wallet,)).fetchone()
    if not row:
        return {"wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0}
    w, loss_n, p = row
    t = w + loss_n
    return {"wins": w, "losses": loss_n, "win_rate": round(w / t, 3) if t else 0.0, "total_pnl": p,
            "confidence": confidence(w, loss_n)}

def confidence(wins: int, losses: int, shrink_n: int = 10) -> float:
    """Confidence 0..1 per wallet: win-rate yang disusutkan saat sampel kecil.
    5W/0L -> ~0.67 (bukan 1.0); 0 trade -> 0.5 (netral, bukan bukti).
    """
    wins, losses = int(wins or 0), int(losses or 0)
    n = wins + losses
    if n == 0:
        return 0.5
    wr = wins / n
    w = min(1.0, n / max(shrink_n, 1))
    return round(0.5 + (wr - 0.5) * w, 3)

def trusted(con: sqlite3.Connection, min_trades: int = 5, min_win_rate: float = 0.6) -> list[str]:
    rows = con.execute("SELECT wallet, wins, losses FROM wallets").fetchall()
    out = []
    for w, wins, losses in rows:
        t = (wins or 0) + (losses or 0)
        if t >= min_trades and (wins / t) >= min_win_rate:
            out.append(w)
    return out

def overlap_bonus(holders: list[str], trusted_wallets: list[str], per_wallet: float = 5.0, max_bonus: float = 15.0,
                  weights: dict[str, float] | None = None) -> tuple[float, int]:
    """Bonus SM bila top holders berisi wallet terpercaya. Return (bonus, n_overlap).
    weights = confidence per wallet (0..1); tanpa weights tiap wallet bobot 1.0 (legacy).
    """
    if not holders or not trusted_wallets:
        return 0.0, 0
    tset = set(trusted_wallets)
    n = 0
    bonus = 0.0
    for h in holders:
        if h in tset:
            n += 1
            bonus += per_wallet * (weights.get(h, 1.0) if weights else 1.0)
    return min(bonus, max_bonus), n
