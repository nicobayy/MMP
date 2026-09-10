"""Meter biaya API: hitung request per sumber per proses.
Tampil di akhir run_scan agar pemakaian kuota Helius/Birdeye terpantau.
Bukan billing presisi — 1 hit = 1 HTTP call (bobot kredit aktual beda per endpoint).

Circuit breaker: set_budgets({"helius": 100}) lalu allow() False bila jatah
habis -> collector fail-closed (return {}) sebelum bakar kuota/kena rate-limit.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()
_counts: dict[str, int] = {}
_budgets: dict[str, int] = {}
_tripped: set[str] = set()

def count(source: str, n: int = 1):
    with _lock:
        _counts[source] = _counts.get(source, 0) + n

def set_budgets(budgets: dict | None):
    global _budgets
    with _lock:
        _budgets = {k: int(v) for k, v in (budgets or {}).items() if int(v) > 0}

def allow(source: str) -> bool:
    """True bila masih ada jatah (atau tanpa budget). Sekali trip -> log warning."""
    with _lock:
        lim = _budgets.get(source)
        if lim is None:
            return True
        if _counts.get(source, 0) >= lim:
            if source not in _tripped:
                _tripped.add(source)
                log.warning("circuit breaker: budget %s=%d habis, %s off sisa run ini", source, lim, source)
            return False
        return True

def summary() -> dict[str, int]:
    with _lock:
        return dict(_counts)

def reset():
    with _lock:
        _counts.clear()
        _tripped.clear()

def line() -> str:
    with _lock:
        counts = dict(_counts)
        budgets = dict(_budgets)
        tripped = sorted(_tripped)
    if not counts:
        return "api: (tak ada call tercatat)"
    parts = [f"{k}={v}" + (f"/{budgets[k]}" if k in budgets else "") for k, v in sorted(counts.items())]
    if tripped:
        parts.append("TRIPPED: " + ",".join(tripped))
    return "api: " + ", ".join(parts)
