"""Seed wallet berkualitas manual (bukan menunggu PASS dulu).
Sumber seed jujur: daftar kurasi sendiri (peneliti on-chain, leaderboard
trainer, dompet yang sudah terbukti di portofolio kamu). MMP TIDAK mengarang
"top trader" — setiap seed berlabel dan tetap harus lolos outcome tracking
(min_trades + win-rate) sebelum bonus scoring aktif.
Usage:
  python scripts/seed_wallets.py --wallet ADDR --label "desc"
  python scripts/seed_wallets.py --file seeds.txt   # ADDR,label per baris (# komentar)
  python scripts/seed_wallets.py --list
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp import validators as _v  # noqa: E402
from mmp.config import db_path  # noqa: E402
from mmp.storage import wallets as wal  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _valid(addr: str, chain: str = "solana") -> bool:
    return _v.is_token_address(chain, addr)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--chain", default="solana")
    ap.add_argument("--file", default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    con = connect(db_path())
    wal.init(con)
    if args.list:
        rows = con.execute("SELECT wallet, label, wins, losses FROM wallets ORDER BY wins DESC LIMIT 100").fetchall()
        if not rows:
            print("DB wallet kosong.")
        for w, lab, wins, losses in rows:
            print(f"{w} [{lab or '-'}] {wins}W/{losses}L")
        return
    items: list[tuple[str, str]] = []
    if args.wallet:
        items.append((args.wallet, args.label))
    if args.file:
        for ln in Path(args.file).read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = [p.strip() for p in ln.split(",", 1)]
            items.append((parts[0], parts[1] if len(parts) > 1 else ""))
    if not items:
        ap.print_help()
        return
    n = 0
    for addr, lab in items:
        if not _valid(addr, args.chain):
            print(f"- skip format salah: {addr[:20]}")
            continue
        wal.set_label(con, addr.strip(), lab, args.chain)
        print(f"+ {addr.strip()[:16]}.. [{lab or '-'}]")
        n += 1
    print(f"Seed tersimpan: {n}. Mereka tetap butuh outcome (paper/manual) sebelum jadi trusted.")

if __name__ == "__main__":
    main()
