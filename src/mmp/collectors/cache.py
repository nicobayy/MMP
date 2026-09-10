"""Cache TTL in-memory untuk respons API yang mahal/rate-limited.
Bukan cache serius terdistribusi — cukup untuk single-operator scanner
agar scan berulang dalam hitungan menit tak membakar kuota.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_store: dict[str, tuple[float, object]] = {}

def get(key: str, ttl: int = 60):
    with _lock:
        hit = _store.get(key)
        if not hit:
            return None
        exp, val = hit
        if time.time() > exp:
            _store.pop(key, None)
            return None
        return val

def put(key: str, value: object, ttl: int = 60):
    with _lock:
        _store[key] = (time.time() + max(ttl, 1), value)

def clear():
    with _lock:
        _store.clear()
