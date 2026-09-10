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

def realized_today(con: sqlite3.Connection, default_sl_pct: float = 15.0) -> float:
    """Rugi/laba hari ini dalam % modal: sum(pnl_pct * risk_pct / sl_pct).

    pnl_pct = return posisi (% harga, bersih biaya), risk_pct = risiko
    % modal per trade (1.0 = 1% modal), sl_pct = jarak SL per trade
    dari kolom entry/sl (|entry-sl|/entry*100, fallback default_sl_pct).
    Contoh: SL -15% dengan risk 1% -> -1% modal; TP +30% -> +2% modal.
    Tanpa pembagi sl_pct, satu SL (-15*1=-15) langsung memicu
    daily-stop -3.0 — itu bug skala yang diperbaiki di sini.
    """
    try:
        rows = con.execute(
            "SELECT pnl_pct, risk_pct, entry, sl FROM paper_positions"
            " WHERE status='CLOSED' AND date(closed_ts)=date('now')"
        ).fetchall()
    except Exception:
        return 0.0
    total = 0.0
    for pnl_pct, risk_pct, entry, sl in rows:
        try:
            pnl = float(pnl_pct or 0)
            risk = float(risk_pct if risk_pct is not None else 1.0)
            sl_dist = default_sl_pct
            if entry and sl:
                sl_dist = abs((float(entry) - float(sl)) / float(entry) * 100)
            if sl_dist <= 0:
                sl_dist = default_sl_pct
            total += pnl * risk / sl_dist
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return float(total)

def allow_new(con: sqlite3.Connection, cfg: dict, chain: str, for_alert: bool = False) -> tuple[bool, str]:
    """Boleh buka paper/alert baru? Return (boleh, alasan).
    Caps (max open/per-chain) hanya menahan paper-open; kill switch &
    daily-stop menahan keduanya agar tak ada aksi saat portofolio panas.
    """
    pf = cfg.get("portfolio") or {}
    if is_killed():
        return False, "KILL SWITCH aktif (data/STOP ada)"
    stop = float(pf.get("daily_stop_pct", -3.0))
    default_sl = float((cfg.get("position") or {}).get("default_stop_loss_pct", 15.0))
    pnl = realized_today(con, default_sl_pct=default_sl)
    if pnl <= stop:
        return False, f"daily-stop: pnl tertimbang hari ini {pnl:.1f} <= {stop}"
    if for_alert:
        return True, "ok"
    if open_count(con) >= int(pf.get("max_open_positions", 5)):
        return False, f"max open {pf.get('max_open_positions', 5)} tercapai"
    if open_per_chain(con).get(chain, 0) >= int(pf.get("max_per_chain", 2)):
        return False, f"max per-chain {chain} ({pf.get('max_per_chain', 2)}) tercapai"
    return True, "ok"
