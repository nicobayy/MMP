"""Backfill MAE/MFE posisi CLOSED lama dari chart DexScreener.

Latar: GeckoTerminal menghapus pool token mati sehingga calibrate +
mae_report tak bisa menilai 44 posisi lama. Chart DexScreener sering
masih menyimpan histori pair mati — skrip ini menarik bar 5-menit
[opened-5m, closed+5m] per posisi dan menulis mae/mfe. Token yang chart-nya
juga hilang -> SKIP jujur.

Hanya menyentuh baris yang mae IS NULL (tak menimpa data rekam-close).
Sopan ke API: jeda antar posisi, timeout pendek, gagal = skip.

Usage (di VPS):
  MMP_DB=data/mmp_sniper.db venv/bin/python scripts/backfill_mae.py [--limit 50]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.collectors import dexscreener as dex  # noqa: E402
from mmp.config import db_path  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _epoch(ts: str) -> int:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill MAE/MFE dari chart DexScreener")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--res", default="5", help="resolusi bar menit (default 5)")
    args = ap.parse_args()
    con = connect(db_path())
    rows = con.execute(
        "SELECT id, symbol, chain, pair_addr, entry, opened_ts, closed_ts"
        " FROM paper_positions WHERE status='CLOSED' AND entry > 0"
        " AND mae IS NULL ORDER BY id LIMIT ?", (int(args.limit),)).fetchall()
    if not rows:
        print("Tidak ada posisi lama tanpa MAE. Selesai.")
        return
    print(f"Backfill {len(rows)} posisi (res={args.res}m, jeda 2 dtk/posisi)...")
    ok = skipped = 0
    for pid, sym, ch, pair, entry, opened, closed in rows:
        start = _epoch(opened)
        end = _epoch(closed) if closed else int(time.time())
        if not start or not end or not pair:
            print(f"#{pid} {sym}: SKIP (data waktu/pair tak lengkap)")
            skipped += 1
            continue
        try:
            bars = dex.get_bars(ch, pair, (start - 300) * 1000, (end + 300) * 1000, res=args.res)
        except Exception as e:
            print(f"#{pid} {sym}: SKIP ({str(e)[:80]})")
            skipped += 1
            time.sleep(2)
            continue
        bars = [b for b in bars if int(b.get("ts", 0)) >= start]
        if not bars:
            print(f"#{pid} {sym}: SKIP (chart tak tersimpan)")
            skipped += 1
            time.sleep(2)
            continue
        try:
            entry_f = float(entry)
            mae = min((float(b["l"]) - entry_f) / entry_f * 100 for b in bars)
            mfe = max((float(b["h"]) - entry_f) / entry_f * 100 for b in bars)
        except (TypeError, ValueError, ZeroDivisionError):
            print(f"#{pid} {sym}: SKIP (bar rusak)")
            skipped += 1
            time.sleep(2)
            continue
        con.execute("UPDATE paper_positions SET mae=?, mfe=? WHERE id=?",
                    (round(mae, 2), round(mfe, 2), pid))
        con.commit()
        print(f"#{pid} {sym}: MAE {mae:.2f}% MFE {mfe:.2f}% ({len(bars)} bar)")
        ok += 1
        time.sleep(2)
    print(f"Selesai: isi={ok} skip={skipped}. Lanjut: mae_report untuk agregat.")


if __name__ == "__main__":
    main()
