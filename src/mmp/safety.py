"""Safety layer: kill switch + portfolio guard.
Kill switch = file data/STOP (atau $MMP_STOP). Ada file = semua run abort.
Portfolio guard = batas portofolio sebelum paper-open / alert baru.
"""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

def stop_file() -> Path:
    return Path(os.getenv("MMP_STOP", "data/STOP"))

def is_killed() -> bool:
    try:
        return stop_file().exists()
    except Exception:
        return False

def open_count(con: sqlite3.Connection) -> int:
    try:
        return int(con.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'").fetchone()[0])
    except Exception:
        return 0

def open_per_chain(con: sqlite3.Connection) -> dict[str, int]:
    try:
        rows = con.execute("SELECT chain, COUNT(*) FROM paper_positions WHERE status='OPEN' GROUP BY chain").fetchall()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}

def realized_today(con: sqlite3.Connection) -> float:
    """Jumlah pnl_pct posisi yang ditutup hari ini (proksi kasar, bukan Rp)."""
    try:
        row = con.execute("SELECT COALESCE(SUM(pnl_pct),0) FROM paper_positions"
                          " WHERE status='CLOSED' AND date(closed_ts)=date('now')").fetchone()
        return float(row[0])
    except Exception:
        return 0.0

def allow_new(con: sqlite3.Connection, cfg: dict, chain: str, for_alert: bool = False) -> tuple[bool, str]:
    """Boleh buka paper/alert baru? Return (boleh, alasan).
    Caps (max open/per-chain) hanya menahan paper-open; kill switch &
    daily-stop menahan keduanya agar tak ada aksi saat portofolio panas.
    """
    pf = cfg.get("portfolio") or {}
    if is_killed():
        return False, "KILL SWITCH aktif (data/STOP ada)"
    stop = float(pf.get("daily_stop_pct", -3.0))
    pnl = realized_today(con)
    if pnl <= stop:
        return False, f"daily-stop: pnl hari ini {pnl:.1f}% <= {stop}%"
    if for_alert:
        return True, "ok"
    if open_count(con) >= int(pf.get("max_open_positions", 5)):
        return False, f"max open {pf.get('max_open_positions', 5)} tercapai"
    if open_per_chain(con).get(chain, 0) >= int(pf.get("max_per_chain", 2)):
        return False, f"max per-chain {chain} ({pf.get('max_per_chain', 2)}) tercapai"
    return True, "ok"
