"""Seed kandidat wallet dari token paper WINNER (bukan semua PASS).

Latar: signal_edge membuktikan winner vs loser identik di semua fitur
tersimpan, dan pipa wallet tak pernah menyala (overlap 0). Satu-satunya
jalan: kandidat dari dompet yang duduk di token yang TERBUKTI naik —
top holder token CLOSED pnl>0. Bukan klaim "smart", cuma kandidat yang
layak dipantau; status trusted tetap wajib lewat win-rate + min_trades
via atribusi outcome yang sudah ada.

Hemat kredit: 1x build_enrichment (4 call) per token winner, sekali jalan.
Jadwalkan whale_watch sesudahnya untuk mengisi arus + atribusi.

Usage (di VPS):
  MMP_DB=data/mmp_sniper.db venv/bin/python scripts/seed_winners.py --limit 40
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.collectors import helius as hel  # noqa: E402
from mmp.config import db_path  # noqa: E402
from mmp.storage import wallets as wal  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed wallet dari token winner")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--holders", type=int, default=10)
    ap.add_argument("--min-pnl", type=float, default=0.0)
    args = ap.parse_args()
    if not hel.has_key():
        print("HELIUS_API_KEY kosong. Isi .env dulu.")
        return
    con = connect(db_path())
    wal.init(con)
    rows = con.execute(
        "SELECT DISTINCT token, symbol FROM paper_positions"
        " WHERE status='CLOSED' AND pnl_pct > ? AND token <> ''"
        " ORDER BY id DESC LIMIT ?", (float(args.min_pnl), int(args.limit),)).fetchall()
    print(f"Token winner: {len(rows)}")
    n_sight = n_tok = 0
    for token, symbol in rows:
        try:
            en = hel.build_enrichment(token, {})
        except Exception as e:
            print(f"- skip {symbol}: {str(e)[:100]}")
            continue
        holders = (en.get("holder_accounts") or [])[: max(int(args.holders), 1)]
        if not holders:
            print(f"- skip {symbol}: tanpa holder")
            continue
        for acct in holders:
            try:
                wal.add_sighting(con, acct, token, symbol or "")
                n_sight += 1
            except Exception:
                continue
        n_tok += 1
    print(f"OK: {n_sight} sightings dari {n_tok} token. Lanjut: whale_watch terjadwal, "
          f"lalu trusted terbentuk sendiri via atribusi (min_trades + win-rate).")


if __name__ == "__main__":
    main()
