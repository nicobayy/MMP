"""Ops health-check harian (anti-lupa): status tiap feed dalam 1 layar.
Usage: python scripts/ops_check.py
Cek: kill switch, scan terakhir, sinyal hari ini, kesegaran whale_watch,
posisi OPEN, callout KOL 7 hari, cakupan. STALE bila melewati ambang wajar.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp import safety as guard  # noqa: E402
from mmp.config import db_path  # noqa: E402
from mmp.storage import stats as stats_mod  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _one(con, q, args=()):
    try:
        row = con.execute(q, args).fetchone()
        return row[0] if row else None
    except Exception:
        return None

def main():
    con = connect(db_path())
    print("=== MMP OPS CHECK ===")
    print(f"[{'KILLED' if guard.is_killed() else 'RUNNING '}] kill switch")
    last_scan = _one(con, "SELECT MAX(ts) FROM signals")
    n_today = _one(con, "SELECT COUNT(*) FROM signals WHERE date(ts)=date('now')") or 0
    print(f"[{'OK ' if last_scan else 'EMPTY'}] scan terakhir: {last_scan} | sinyal hari ini: {n_today}")
    whale_last = _one(con, "SELECT MAX(ts) FROM whale_buys")
    whale_n = _one(con, "SELECT COUNT(*) FROM whale_buys WHERE ts >= datetime('now','-26 hours')") or 0
    stale_w = not whale_last or str(whale_last) < str(_one(con, "SELECT datetime('now','-26 hours')"))
    print(f"[{'STALE' if stale_w else 'OK   '}] whale_watch terakhir: {whale_last} | buys 26h: {whale_n}")
    n_open = _one(con, "SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'") or 0
    n_closed = _one(con, "SELECT COUNT(*) FROM paper_positions WHERE status='CLOSED'") or 0
    print(f"[INFO ] paper OPEN={n_open} CLOSED={n_closed} (target bukti: >=20/ tier)")
    kol7 = _one(con, "SELECT COUNT(*) FROM kol_callouts WHERE ts >= datetime('now','-7 days')") or 0
    print(f"[{'STALE' if kol7 == 0 else 'OK   '}] callout KOL 7 hari: {kol7} (manual, jadikan kebiasaan)")
    rep = stats_mod.coverage_report(con)
    print(f"[INFO ] cakupan: batch={rep['batches']} blind={rep['blind_pct']}% hp_gap={rep['hp_gap_pct']}%")

if __name__ == "__main__":
    main()
