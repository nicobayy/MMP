"""Report rutin MMP: bukti low-risk berkala, bukan klaim.
Usage: python scripts/report.py
Isi: paper per-tier (n, winrate, expectancy, max DD), veto terbanyak,
cakupan data, KOL PAPER thay vì: sudah tercakup via calibrate.
n < 20 per tier = EXPLORATORY (jangan geser threshold).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.backtest.engine import expectancy  # noqa: E402
from mmp.config import db_path  # noqa: E402
from mmp.storage import stats as stats_mod  # noqa: E402
from mmp.storage.store import connect  # noqa: E402

MIN_N = 20

def _max_dd(pnls: list[float]) -> float:
    peak = 0.0
    dd = 0.0
    eq = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return round(dd, 2)

def main():
    con = connect(db_path())
    print("=== MMP REPORT (bukti, bukan klaim) ===")
    for tier in (1, 2):
        rows = con.execute("SELECT pnl_pct, close_reason FROM paper_positions"
                           " WHERE status='CLOSED' AND COALESCE(tier,1)=? ORDER BY id", (tier,)).fetchall()
        if not rows:
            print(f"TIER-{tier}: belum ada closed.")
            continue
        pnls = [float(r[0] or 0) for r in rows]
        wins = [x for x in pnls if x > 0]
        losses = [x for x in pnls if x <= 0]
        wr = len(wins) / len(pnls)
        aw = sum(wins) / len(wins) if wins else 0.0
        al = abs(sum(losses) / len(losses)) if losses else 0.0
        exp = expectancy(wr, aw, al)
        flag = "OK" if len(pnls) >= MIN_N and exp > 0 else ("EXPLORATORY" if len(pnls) < MIN_N else "NEGATIVE")
        print(f"TIER-{tier}: n={len(pnls)} wr={wr:.0%} exp={exp:.2f} maxDD={_max_dd(pnls)} [{flag}]")
    print("--- veto terbanyak ---")
    try:
        from collections import Counter
        c: Counter = Counter()
        for (reason,) in con.execute("SELECT reason FROM signals WHERE verdict='REJECT'").fetchall():
            first = (reason or "").split("|")[0].strip()
            if "VETO:" in first:
                for v in first.replace("VETO:", "").split(";"):
                    v = v.strip().split(":")[0]
                    if v:
                        c[v] += 1
            else:
                c["CONF_BELOW_THRESHOLD"] += 1
        for k, v in c.most_common(8):
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"  (skip: {e})")
    print("--- cakupan ---")
    rep = stats_mod.coverage_report(con)
    print(f"  batch={rep['batches']} sinyal={rep['signals']} "
          f"COMPLETE {rep['complete_pct']}% BLIND {rep['blind_pct']}% hp_gap {rep['hp_gap_pct']}%")

if __name__ == "__main__":
    main()
