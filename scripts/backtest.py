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
from mmp.collectors import dexscreener as dex
from mmp.storage.store import connect
from mmp.backtest.engine import settle, summarize

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    cfg = load_config()
    con = connect(db_path())
    sl_pct = float(cfg["position"]["default_stop_loss_pct"])
    tp_pct = float(cfg["position"]["default_take_profit_pct"])
    rows = con.execute("SELECT symbol, chain, token, pair_addr, price, payload FROM signals"
                       " WHERE verdict='PASS' ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
    if not rows:
        print("Belum ada sinyal PASS. Backtest butuh data dulu — jalankan scan rutin / paper trading.")
        return
    outcomes = []
    for sym, chain, token, pair_addr, entry, _ in rows:
        try:
            pairs = dex.get_token_pairs(chain, token)
            best = dex.pick_best_pair(pairs) if pairs else None
            now = float((best or {}).get("priceUsd") or 0)
        except Exception:
            now = 0.0
        if not now:
            continue
        r = settle(entry, now, sl_pct, tp_pct)
        outcomes.append({"symbol": sym, **r})
        print(f"- {sym}: entry=${entry} now=${now} -> {r['status']} {r['pnl_pct']}%")
    print(json.dumps(summarize(outcomes), indent=2))

if __name__ == "__main__":
    main()
