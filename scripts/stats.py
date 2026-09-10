"""Lihat tren cakupan data antar batch: python scripts/stats.py
Aturan baca (lihat storage/stats.py):
- hp_gap_pct < 10% -> tak layak tambah sumber baru.
- hp_gap_pct > 50% -> bottleneck nyata, justifikasi fallback berlapis
  (mis. GoPlus), tetap fail-closed.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path  # noqa: E402
from mmp.storage import stats as stats_mod  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def main():
    con = connect(db_path())
    rep = stats_mod.coverage_report(con)
    if not rep["batches"]:
        print("Belum ada data batch. Jalankan scan dulu (otomatis tercatat tiap run).")
        return
    print(f"batch: {rep['batches']} | sinyal: {rep['signals']}")
    print(f"grade: COMPLETE {rep['complete_pct']}% / PARTIAL {rep['partial_pct']}% / BLIND {rep['blind_pct']}%")
    print(f"honeypot.is EVM: tax-ok {rep['hp_tax_ok_pct']}% / gap {rep['hp_gap_pct']}%")
    if rep["signals"] < 20:
        print(f"-> data BELUM CUKUP ({rep['signals']}/20 sinyal): kumpulkan dulu sebelum putuskan.")
    elif rep["hp_gap_pct"] > 50:
        print("-> bottleneck NYATA: layak pertimbangkan fallback berlapis (fail-closed).")
    elif rep["hp_gap_pct"] < 10:
        print("-> cakupan SEHAT: tak perlu sumber tambahan.")
    else:
        print("-> zona ABU-ABU: lanjutkan pengukuran.")

if __name__ == "__main__":
    main()
