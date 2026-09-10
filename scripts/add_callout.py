"""Catat KOL callout manual.
Usage:
  python scripts/add_callout.py --token MINT --symbol XYZ --handle @kanal --trusted --source telegram
  python scripts/add_callout.py --list --token MINT
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path
from mmp.storage.store import connect
from mmp.storage import kol as koldb

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=None)
    ap.add_argument("--symbol", default="")
    ap.add_argument("--chain", default="solana")
    ap.add_argument("--source", default="telegram")
    ap.add_argument("--handle", default="")
    ap.add_argument("--trusted", action="store_true")
    ap.add_argument("--note", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    con = connect(db_path())
    koldb.init(con)
    if args.list:
        rows = koldb.recent_for_token(con, args.token or "", hours=24 * 30)
        if not rows:
            print("Belum ada callout untuk token itu.")
        for r in rows:
            print(f"[{'TRUSTED' if r['trusted'] else 'biasa'}] {r['handle']} via {r['source']} @ {r['ts']}")
        return
    if not args.token:
        ap.print_help(); return
    rid = koldb.add_callout(con, args.token, args.symbol, args.chain, args.source, args.handle, args.trusted, args.note)
    print(f"OK callout #{rid} tersimpan (trusted={args.trusted}). Skor KOL aktif 48 jam ke depan.")

if __name__ == "__main__":
    main()
