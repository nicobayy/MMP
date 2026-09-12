"""Kalibrasi skor -> probabilitas riil per bucket, split per tier.
Usage: python scripts/calibrate.py [--min-n 5]
Sumber: posisi paper CLOSED (entry/SL/TP/entry-time riil) + replay candle.
Jangan gabung tier: TIER-1 full-size vs TIER-2 half-size profilnya beda.
n kecil = belum kesimpulan (ditandai EXPLORATORY).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.backtest.engine import apply_costs, effective_costs  # noqa: E402
from mmp.backtest.replay import calibrate, replay  # noqa: E402
from mmp.collectors import ohlcv  # noqa: E402
from mmp.config import db_path, load_config  # noqa: E402
from mmp.storage import candles as cstore  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _epoch(ts) -> int:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config()
    min_n = int(args.min_n) if args.min_n is not None else int((cfg.get("backtest") or {}).get("min_n_per_bucket", 5))
    con = connect(db_path())
    cstore.init(con)
    slip = float((cfg.get("paper") or {}).get("slippage_pct", 0.5))
    fee = float((cfg.get("paper") or {}).get("fee_pct", 0.2))
    timeout_h = float((cfg.get("paper") or {}).get("timeout_h", 72))
    positions = con.execute("SELECT id, symbol, chain, token, entry, sl, tp, opened_ts, tier FROM paper_positions"
                            " WHERE status='CLOSED' ORDER BY id DESC LIMIT 200").fetchall()
    if not positions:
        print("Belum ada posisi paper CLOSED. Kalibrasi butuh data — jalankan scheduler + settle dulu.")
        return
    rows = []
    for pid, sym, chain, token, entry, sl, tp, opened, tier in positions:
        if not entry:
            continue
        sl_pct = abs((entry - (sl or entry * 0.85)) / entry * 100)
        tp_pct = abs(((tp or entry * 1.3) - entry) / entry * 100)
        # M3: join STRICT via signal_id (kolom paper baru). Paper lama tanpa
        # signal_id -> SKIP dengan pesan, bukan heuristik token+harga yang
        # bisa menempelkan confidence token lain.
        sig = None
        try:
            prow = con.execute("SELECT signal_id FROM paper_positions WHERE id=?", (pid,)).fetchone()
            if prow and prow[0]:
                sig = con.execute("SELECT payload FROM signals WHERE id=?", (prow[0],)).fetchone()
        except Exception:
            sig = None
        if not sig:
            print(f"- #{pid} {sym}: tanpa signal_id (paper lama), skip agar tak salah atribusi")
            continue
        try:
            _d = json.loads((sig or ["{}"])[0])
            conf = float(_d.get("confidence", 0))
            _liq = ((_d.get("meta") or {}).get("liquidity") or {}).get("liquidity_usd")
            _slip, _fee = effective_costs(_liq, slip, fee, cfg)
        except Exception:
            conf = 0.0
            _slip, _fee = slip, fee
        pool = ohlcv.resolve_pool(chain, token or "")
        if not pool:
            print(f"- #{pid} {sym}: pool tak ditemukan, skip")
            continue
        candles = cstore.get_candles(con, chain, pool, "hour", since=_epoch(opened) - 3600)
        if not candles:
            candles = ohlcv.fetch(chain, pool, "hour", int((cfg.get("backtest") or {}).get("replay_limit", 500)))
            cstore.upsert_candles(con, chain, pool, "hour", candles)
        r = replay(_epoch(opened), float(entry), sl_pct, tp_pct, candles, timeout_h=timeout_h)
        r["pnl_pct"] = apply_costs(r["pnl_pct"], _slip, _fee)
        rows.append({"conf": conf, "tier": tier or 1, **r})
        print(f"- #{pid} {sym} T{tier or 1} conf={conf}: {r['status']} {r['pnl_pct']}%")
    print()
    rep = calibrate(rows)
    for k, v in rep.items():
        flag = "OK" if v["n"] >= min_n and v["expectancy"] > 0 else ("EXPLORATORY" if v["n"] < min_n else "NEGATIVE")
        print(f"{k}: n={v['n']} wr={v['winrate']} exp={v['expectancy']} MFE={v['avg_mfe']} MAE={v['avg_mae']} [{flag}]")
    if not rep:
        print("Tak ada outcome TP/SL/TIMEOUT/TRAIL untuk dikalibrasi.")

if __name__ == "__main__":
    main()
