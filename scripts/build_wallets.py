"""Kumpulkan kandidat wallet dari token PASS terakhir via Helius top holders.
Hemat kredit: hanya token PASS (sedikit), hanya Solana.
Usage: python scripts/build_wallets.py --limit 20
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.collectors import helius as hel
from mmp.config import db_path, load_config
from mmp.storage import wallets as wal
from mmp.storage.store import connect


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    cfg = load_config()
    if not hel.has_key():
        print("HELIUS_API_KEY kosong. Isi .env dulu.")
        return
    con = connect(db_path())
    wal.init(con)
    rows = con.execute("SELECT DISTINCT token, symbol FROM signals WHERE verdict='PASS' AND chain='solana' ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
    print(f"Cek {len(rows)} token PASS...")
    n = 0
    for token, symbol in rows:
        try:
            en = hel.build_enrichment(token, cfg)
            for acct in en.get("holder_accounts", [])[:10]:
                wal.add_sighting(con, acct, token, symbol or "")
                n += 1
        except Exception as e:
            print(f"- skip {symbol}: {e}")
    print(f"OK: {n} sightings tersimpan. Catat outcome via record_outcome.py agar win-rate terbentuk.")

if __name__ == "__main__":
    main()
