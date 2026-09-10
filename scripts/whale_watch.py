"""Pantau aktivitas whale: swap terakhir wallet tracked via Helius enhanced txns.
Usage: python scripts/whale_watch.py [--wallets 10] [--sigs 20]
Alur: trusted (atau kandidat tersering bila belum ada) -> signature terakhir
-> parse enhanced -> catat BUY/SELL per token ke whale_buys.
Butuh HELIUS_API_KEY. Hemat: batasi wallet & signature via config tracker.
Jadwalkan tiap 1-2 jam TERPISAH dari scan agar kredit terkendali.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.collectors import helius as hel  # noqa: E402
from mmp.collectors import meter as _meter  # noqa: E402
from mmp.config import db_path, load_config  # noqa: E402
from mmp.storage import wallets as wal  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallets", type=int, default=None)
    ap.add_argument("--sigs", type=int, default=None)
    args = ap.parse_args()
    cfg = load_config()
    _meter.set_budgets(cfg.get("api_budgets"))
    if not hel.has_key():
        print("HELIUS_API_KEY kosong. Isi .env dulu.")
        return
    tr = cfg.get("tracker") or {}
    n_w = args.wallets or int(tr.get("watch_wallets", 10))
    n_s = args.sigs or int(tr.get("watch_sigs", 20))
    con = connect(db_path())
    wal.init(con)
    watched = wal.trusted(con, int(tr.get("min_trades", 5)), float(tr.get("min_win_rate", 0.6)))
    if not watched:
        watched = wal.top_watched(con, n_w)
        print(f"Belum ada trusted: pantau {len(watched)} kandidat tersering (bootstrap).")
    else:
        watched = watched[:n_w]
    if not watched:
        print("DB wallet kosong. Jalankan scan PASS + Helius dulu untuk isi kandidat.")
        return
    n_new = 0
    for w in watched:
        try:
            sigs = hel.get_signatures(w, n_s)
            if not sigs:
                continue
            txns = hel.parse_enhanced(sigs)
            for f in hel.wallet_token_flows(w, txns):
                if wal.record_whale_flow(con, w, f["mint"], f["side"], f["amount"],
                                         f["signature"], f.get("sol_spent", 0.0)):
                    n_new += 1
                    if f["side"] == "BUY":
                        print(f"  BUY {w[:8]}.. -> {f['mint'][:8]}.. amt={f['amount']} sol~{f.get('sol_spent', 0)}")
            print(f"- {w[:12]}..: {len(sigs)} sigs, {len(txns)} parsed")
        except Exception as e:
            print(f"- {w[:12]}..: skip ({str(e)[:120]})")
    print(f"Whale baru tercatat: {n_new} | {_meter.line()}")

if __name__ == "__main__":
    main()
