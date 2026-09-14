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
    tf_cfg = str((cfg.get("backtest") or {}).get("replay_tf", "hour"))
    if tf_cfg not in ("minute", "hour", "day"):
        tf_cfg = "hour"
    con = connect(db_path())
    pstore.init(con)
    cstore.init(con)

    def _pool_candles(ch: str, pool: str, start: int, end: int, opened_epoch: int):
        # Coba TF config dulu, lalu TF lain: jangan SKIP hanya karena env
        # MMP_CONFIG lupa diisi (filter=hour vs sniper=minute).
        for tf in dict.fromkeys([tf_cfg, "minute", "hour", "day"]):
            try:
                cs = [c for c in cstore.get_candles(con, ch, pool, tf, since=start)
                      if start <= int(c.get("ts", 0)) <= end
                      and int(c.get("ts", 0)) >= opened_epoch]
            except Exception:
                continue
            if cs:
                return cs, tf
        return [], tf_cfg
    rows = con.execute(
        "SELECT id, symbol, chain, entry, opened_ts, closed_ts, close_reason, pnl_pct,"
        " COALESCE(pool,''), mae, mfe FROM paper_positions"
        " WHERE status='CLOSED' AND entry > 0 ORDER BY id").fetchall()
    if not rows:
        print("Belum ada posisi CLOSED.")
        return
    try:
        db_candles = con.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    except Exception:
        db_candles = 0
    print(f"cache candles di DB: {db_candles} baris (bila 0, cache memang kosong)")
    wins_mae: list[float] = []
    wicked = 0
    n_win = 0
    for pid, sym, ch, entry, opened, closed, reason, pnl, pool, col_mae, col_mfe in rows:
        if col_mae is not None or col_mfe is not None:
            mae = float(col_mae) if col_mae is not None else 0.0
            mfe = float(col_mfe) if col_mfe is not None else 0.0
            n_c, src = "-", "rekam-close"
            win = float(pnl or 0) > 0
            if win:
                n_win += 1
                wins_mae.append(mae)
                if mae <= -abs(args.sl):
                    wicked += 1
            print(f"#{pid} {sym} {reason} {pnl}%: MAE {mae}% MFE {mfe}% ({n_c} candle, {src})")
            continue
        start = _epoch(opened) - 3600
        end = _epoch(closed) if closed else int(datetime.now(timezone.utc).timestamp())
        opened_epoch = _epoch(opened)
        src = "rekam"
        tf_use = tf_cfg
        if not pool:
            tf_use = ""
            for tf_try in dict.fromkeys([tf_cfg, "minute", "hour", "day"]):
                try:
                    cands = con.execute(
                        "SELECT DISTINCT pool FROM candles WHERE chain=? AND tf=?"
                        " AND ts>=? AND ts<=?", (ch, tf_try, start, end)).fetchall()
                except Exception:
                    continue
                pools = [r[0] for r in cands if r[0]]
                if len(pools) == 1:
                    pool, src, tf_use = pools[0], "tebak-1", tf_try
                    break
            if not tf_use:
                print(f"#{pid} {sym}: SKIP (pool tak pasti, tak ditebak)")
                continue
        cs, tf_hit = _pool_candles(ch, pool, start, end, opened_epoch)
        if tf_hit != tf_use:
            src += f"/tf-{tf_hit}"
        # Hanya aksi SETELAH entry yang adil dinilai; candle sejam pra-entry
        # (buffer `since`) wajib dibuang agar MAE/MFE tak bocor data lama.
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
