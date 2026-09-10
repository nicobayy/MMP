"""Catat hasil trade per wallet untuk membentuk win-rate.
Usage: python scripts/record_outcome.py --wallet ADDR --win --pnl 12.5
       python scripts/record_outcome.py --wallet ADDR --loss --pnl -5
       python scripts/record_outcome.py --list
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path
from mmp.storage import wallets as wal
from mmp.storage.store import connect


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", default=None)
    ap.add_argument("--win", action="store_true")
    ap.add_argument("--loss", action="store_true")
    ap.add_argument("--pnl", type=float, default=0.0)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    con = connect(db_path())
    wal.init(con)
    if args.list:
        rows = list(con.execute("SELECT wallet, wins, losses, total_pnl FROM wallets ORDER BY wins DESC LIMIT 50"))
        if not rows:
            print("Belum ada wallet tracked. Wallet terkumpul otomatis tiap ada sinyal PASS Solana + Helius on.")
            return
        for r in rows:
            w, wins, losses, pnl = r
            t = wins + losses
            wr = (wins / t) if t else 0
            print(f"{w} | {wins}W/{losses}L wr={wr:.0%} pnl={pnl}")
        return
    if not args.wallet or (not args.win and not args.loss):
        ap.print_help()
        return
    wal.record_outcome(con, args.wallet, win=args.win, pnl=args.pnl)
    print("OK:", wal.stats(con, args.wallet))

if __name__ == "__main__":
    main()
