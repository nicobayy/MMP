"""Lapor MAE/MFE posisi CLOSED dari candle cache DB (bukan API live).

Kenapa cache: token meme mati hilang dari GeckoTerminal, jadi
scripts/calibrate.py (resolve pool live) gagal total untuk histori sniper.
Cache ditulis tiap round settle saat token masih hidup.

Pool diambil dari kolom paper_positions.pool (direkam saat settle);
posisi lama tanpa pool dicocokkan heuristik overlap waktu dan dipakai
hanya bila tepat 1 kandidat — selain itu SKIP jujur, bukan tebak.

Usage (di VPS):
  MMP_DB=data/mmp_sniper.db MMP_CONFIG=config/mmp_sniper.yaml \
    venv/bin/python scripts/mae_report.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path, load_config  # noqa: E402
from mmp.storage import candles as cstore  # noqa: E402
from mmp.storage import paper as pstore  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _epoch(ts: str) -> int:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def _mae_mfe(entry: float, candles: list[dict]) -> tuple[float, float]:
    mfe, mae = 0.0, 0.0
    for c in candles:
        try:
            hi, lo = float(c["h"]), float(c["l"])
        except (KeyError, TypeError, ValueError):
            continue
        mfe = max(mfe, (hi - entry) / entry * 100)
        mae = min(mae, (lo - entry) / entry * 100)
    return round(mae, 2), round(mfe, 2)


def main() -> None:
    ap = argparse.ArgumentParser(description="MAE/MFE CLOSED dari candle cache")
    ap.add_argument("--sl", type=float, default=6.0,
                    help=" garis SL untuk hitung wick-out (default 6)")
    args = ap.parse_args()
    cfg = load_config()
    tf = str((cfg.get("backtest") or {}).get("replay_tf", "hour"))
    if tf not in ("minute", "hour", "day"):
        tf = "hour"
    con = connect(db_path())
    pstore.init(con)
    cstore.init(con)
    rows = con.execute(
        "SELECT id, symbol, chain, entry, opened_ts, closed_ts, close_reason, pnl_pct,"
        " COALESCE(pool,'') FROM paper_positions"
        " WHERE status='CLOSED' AND entry > 0 ORDER BY id").fetchall()
    if not rows:
        print("Belum ada posisi CLOSED.")
        return
    wins_mae: list[float] = []
    wicked = 0
    n_win = 0
    for pid, sym, ch, entry, opened, closed, reason, pnl, pool in rows:
        start = _epoch(opened) - 3600
        end = _epoch(closed) if closed else int(datetime.now(timezone.utc).timestamp())
        src = "rekam"
        if not pool:
            try:
                cands = con.execute(
                    "SELECT DISTINCT pool FROM candles WHERE chain=? AND tf=?"
                    " AND ts>=? AND ts<=?", (ch, tf, start, end)).fetchall()
            except Exception:
                cands = []
            pools = [r[0] for r in cands if r[0]]
            if len(pools) != 1:
                print(f"#{pid} {sym}: SKIP (kandidat pool={len(pools)}, tak ditebak)")
                continue
            pool, src = pools[0], "tebak-1"
        cs = [c for c in cstore.get_candles(con, ch, pool, tf, since=start)
              if int(c.get("ts", 0)) <= end]
        if not cs:
            print(f"#{pid} {sym}: SKIP (cache kosong)")
            continue
        mae, mfe = _mae_mfe(float(entry), cs)
        win = float(pnl or 0) > 0
        if win:
            n_win += 1
            wins_mae.append(mae)
            if mae <= -abs(args.sl):
                wicked += 1
        print(f"#{pid} {sym} {reason} {pnl}%: MAE {mae}% MFE {mfe}% ({len(cs)} candle, pool {src})")
    print(f"\nWinner: {n_win}, rata-rata MAE winner: "
          f"{round(sum(wins_mae) / len(wins_mae), 2) if wins_mae else 0}%")
    print(f"Winner yang sempat < -{args.sl}% (wick-out nyaris): {wicked}/{n_win}")
    if n_win:
        print("Baca: bila wick-out sering tapi tetap TP, SL lebih lebar + TP lebih jauh layak diuji.")


if __name__ == "__main__":
    main()
