"""Replay candle-accurate untuk sinyal PASS: TP/SL mana kena duluan + MFE/MAE.
Usage: python scripts/replay.py --limit 10 [--tf hour]
Alur per sinyal: resolve pool Gecko -> fetch candle -> simpan DB -> replay
dari timestamp sinyal. Jujur: butuh candle SETELAH entry; sinyal kemarin
punya data, sinyal 5 menit lalu belum.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.backtest.engine import apply_costs  # noqa: E402
from mmp.backtest.replay import replay  # noqa: E402
from mmp.collectors import ohlcv  # noqa: E402
from mmp.config import db_path, load_config  # noqa: E402
from mmp.storage import candles as cstore  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _epoch(ts) -> int:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # CURRENT_TIMESTAMP = UTC
        return int(dt.timestamp())
    except Exception:
        return 0

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--tf", default="hour")
    args = ap.parse_args()
    cfg = load_config()
    con = connect(db_path())
    cstore.init(con)
    sl_pct = float(cfg["position"]["default_stop_loss_pct"])
    tp_pct = float(cfg["position"]["default_take_profit_pct"])
    slip = float((cfg.get("paper") or {}).get("slippage_pct", 0.5))
    fee = float((cfg.get("paper") or {}).get("fee_pct", 0.2))
    rows = con.execute("SELECT id, symbol, chain, token, price, ts, payload FROM signals"
                       " WHERE verdict='PASS' ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
    if not rows:
        print("Belum ada sinyal PASS untuk di-replay.")
        return
    for sid, sym, chain, token, entry, ts, payload in rows:
        try:
            tier = json.loads(payload or "{}").get("tier", 1)
        except Exception:
            tier = 1
        pool = ohlcv.resolve_pool(chain, token)
        if not pool:
            print(f"- #{sid} {sym}: pool tak ditemukan, skip")
            continue
        candles = cstore.get_candles(con, chain, pool, args.tf, since=_epoch(ts) - 3600)
        if not candles:
            candles = ohlcv.fetch(chain, pool, args.tf, int((cfg.get("backtest") or {}).get("replay_limit", 500)))
            cstore.upsert_candles(con, chain, pool, args.tf, candles)
        r = replay(_epoch(ts), float(entry or 0), sl_pct, tp_pct, candles,
                   timeout_h=float((cfg.get("paper") or {}).get("timeout_h", 72)))
        r["pnl_pct"] = apply_costs(r["pnl_pct"], slip, fee)
        print(f"- #{sid} {sym} T{tier}: {r['status']} {r['pnl_pct']}% (MFE {r['mfe']}% MAE {r['mae']}% bars {r['bars']})")

if __name__ == "__main__":
    main()
