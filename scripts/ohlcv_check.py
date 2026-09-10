"""Cek depth histori OHLCV GeckoTerminal (tier gratis) per pool.
Usage: python scripts/ohlcv_check.py --chain base --pool 0xABC... [--tf hour]
Tanpa argumen: tampilkan coverage candle yang sudah tersimpan di DB lokal.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.collectors import ohlcv  # noqa: E402
from mmp.config import db_path  # noqa: E402
from mmp.storage import candles as cstore  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _fmt(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default=None)
    ap.add_argument("--pool", default=None)
    ap.add_argument("--tf", default="hour")
    args = ap.parse_args()
    if args.chain and args.pool:
        d = ohlcv.depth(args.chain, args.pool)
        print(f"{args.chain} {args.pool[:10]}... tf={args.tf}: "
              f"n={d['n_hour']} oldest={_fmt(d['oldest'])} newest={_fmt(d['newest'])}")
        if not d["n_hour"]:
            print("KOSONG: tier gratis tak menyimpan histori pool ini (atau pool salah).")
        return
    con = connect(db_path())
    cstore.init(con)
    cov = cstore.coverage(con)
    if not cov:
        print("DB candle kosong. Isi via replay (otomatis fetch) atau ohlcv_check --chain --pool.")
    for c in cov:
        print(f"{c['chain']} {c['pool'][:10]}... {c['tf']}: n={c['n']} {_fmt(c['oldest'])} -> {_fmt(c['newest'])}")

if __name__ == "__main__":
    main()
