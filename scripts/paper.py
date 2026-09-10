"""Paper trading CLI.
Usage:
  python scripts/paper.py --list
  python scripts/paper.py --settle            # tutup yg kena TP/SL/timeout
  python scripts/paper.py --settle --timeout-h 24
  python scripts/paper.py --report            # expectancy dari posisi closed
"""
from __future__ import annotations
import json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import load_config, db_path
from mmp.collectors import dexscreener as dex
from mmp.storage.store import connect
from mmp.storage import paper as pstore
from mmp.backtest.engine import settle, summarize, apply_costs

def live_price(chain: str, pair_addr: str) -> float:
    try:
        p = dex.get_pair(chain, pair_addr)
        return float((p or {}).get("priceUsd") or 0)
    except Exception:
        return 0.0

def age_hours(opened_ts: str) -> float:
    try:
        dt = datetime.fromisoformat(str(opened_ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # CURRENT_TIMESTAMP = UTC
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 0.0

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--settle", action="store_true")
    ap.add_argument("--timeout-h", type=float, default=None)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    con = connect(db_path())
    pstore.init(con)
    sl_pct = float(cfg["position"]["default_stop_loss_pct"])
    tp_pct = float(cfg["position"]["default_take_profit_pct"])
    slip = float((cfg.get("paper") or {}).get("slippage_pct", 0.5))
    fee = float((cfg.get("paper") or {}).get("fee_pct", 0.2))
    timeout_h = float(args.timeout_h) if args.timeout_h is not None \
        else float((cfg.get("paper") or {}).get("timeout_h", 72))

    if args.list or not (args.settle or args.report):
        opens = pstore.list_open(con)
        if not opens:
            print("Tidak ada posisi paper OPEN.")
        for o in opens:
            print(f"#{o['id']} {o['symbol']} {o['chain']} entry=${o['entry']} SL=${o['sl']} TP=${o['tp']}")
    if args.settle:
        n = 0
        for o in pstore.list_open(con):
            px = live_price(o["chain"], o["pair_addr"])
            if not px:
                print(f"- skip {o['symbol']}: harga tak tersedia"); continue
            timed_out = age_hours(o.get("opened_ts", "")) >= timeout_h
            r = settle(o["entry"], px, sl_pct, tp_pct, timeout_hit=timed_out)
            if r["status"] in ("TP", "SL", "TIMEOUT"):
                net = apply_costs(r["pnl_pct"], slip, fee)
                pstore.close_position(con, o["id"], px, net, r["status"])
                print(f"- closed #{o['id']} {o['symbol']} {r['status']} {net}% (gross {r['pnl_pct']}%)"); n += 1
            else:
                print(f"- open #{o['id']} {o['symbol']} {r['pnl_pct']}%")
        print(f"Settled {n} posisi (timeout {timeout_h}h).")
    if args.report:
        rows = con.execute("SELECT pnl_pct, close_reason, COALESCE(tier,1) FROM paper_positions WHERE status='CLOSED'").fetchall()
        outcomes = [{"status": r[1], "pnl_pct": r[0]} for r in rows]
        rep = summarize(outcomes)
        print("Paper report (semua tier):", json.dumps(rep, indent=2))
        for t in (1, 2):
            to = [{"status": r[1], "pnl_pct": r[0]} for r in rows if r[2] == t]
            if to:
                print(f"Paper report TIER-{t}:", json.dumps(summarize(to), indent=2))
        if rep.get("n", 0) and rep["expectancy"] <= 0:
            print("WARNING: expectancy <= 0 — jangan pakai uang asli, tune config dulu.")

if __name__ == "__main__":
    main()
