"""Backtest report: ukur return sinyal PASS (entry DB vs harga live sekarang).
Usage: python scripts/backtest.py --limit 50
Jujur: ini forward-measure, bukan backtest candle. Untuk validasi expectancy awal.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import load_config, db_path
from mmp.collectors import prices as pxr
from mmp.storage.store import connect
from mmp.backtest.engine import settle, summarize, apply_costs

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    cfg = load_config()
    con = connect(db_path())
    sl_pct = float(cfg["position"]["default_stop_loss_pct"])
    tp_pct = float(cfg["position"]["default_take_profit_pct"])
    slip = float((cfg.get("paper") or {}).get("slippage_pct", 0.5))
    fee = float((cfg.get("paper") or {}).get("fee_pct", 0.2))
    print(f"(PnL bersih setelah biaya asumsi {slip}% slip + {fee}% fee per sisi)")
    rows = con.execute("SELECT symbol, chain, token, pair_addr, price, payload FROM signals"
                       " WHERE verdict='PASS' ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
    if not rows:
        print("Belum ada sinyal PASS. Backtest butuh data dulu — jalankan scan rutin / paper trading.")
        return
    outcomes = []
    for sym, chain, token, pair_addr, entry, _ in rows:
        now, src = pxr.resolve_price(chain, token, pair_addr)
        if not now:
            continue
        r = settle(entry, now, sl_pct, tp_pct)
        r["pnl_pct"] = apply_costs(r["pnl_pct"], slip, fee)
        outcomes.append({"symbol": sym, **r})
        print(f"- {sym}: entry=${entry} now=${now} ({src}) -> {r['status']} {r['pnl_pct']}% (net)")
    print(json.dumps(summarize(outcomes), indent=2))

if __name__ == "__main__":
    main()
