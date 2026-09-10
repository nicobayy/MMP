"""Meter biaya API: hitung request per sumber per proses.
Tampil di akhir run_scan agar pemakaian kuota Helius/Birdeye terpantau.
Bukan billing presisi — 1 hit = 1 HTTP call (bobot kredit aktual beda per endpoint).
"""
from __future__ import annotations

_counts: dict[str, int] = {}

def count(source: str, n: int = 1):
    _counts[source] = _counts.get(source, 0) + n

def summary() -> dict[str, int]:
    return dict(_counts)

def reset():
    _counts.clear()

def line() -> str:
    if not _counts:
        return "api: (tak ada call tercatat)"
    return "api: " + ", ".join(f"{k}={v}" for k, v in sorted(_counts.items()))
