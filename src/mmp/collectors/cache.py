"""Cache TTL in-memory untuk respons API yang mahal/rate-limited.
Bukan cache serius terdistribusi — cukup untuk single-operator scanner
agar scan berulang dalam hitungan menit tak membakar kuota.

M2: cache + budget hidup per-proses (scheduler spawn proses baru tiap
round). Untuk mengurangi fetch ulang antar-round, ada file-cache
ringan di data/cache.json (best-effort, TTL sama). Korup/kunci =
diabaikan, bukan crash.
"""
from __future__ import annotations

import json
import os
import threading
import time

_lock = threading.Lock()
_store: dict[str, tuple[float, object]] = {}

_FILE = os.path.join(os.getenv("MMP_DB_DIR", "data"), "cache.json")


def _load_file() -> dict:
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_file(d: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_FILE) or ".", exist_ok=True)
        tmp = _FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _FILE)
    except Exception:
        pass

def get(key: str, ttl: int = 60):
    with _lock:
        hit = _store.get(key)
        if not hit:
            pass
        else:
            exp, val = hit
            if time.time() <= exp:
                return val
            _store.pop(key, None)
    # M2: fallback file-cache antar-proses (scheduler round baru).
    try:
        d = _load_file()
        row = d.get(key)
        if isinstance(row, list) and len(row) == 2 and time.time() <= float(row[0]):
            with _lock:
                _store[key] = (float(row[0]), row[1])
            return row[1]
    except Exception:
        pass
    return None

def put(key: str, value: object, ttl: int = 60):
    exp = time.time() + max(ttl, 1)
    with _lock:
        _store[key] = (exp, value)
    # M2: persist best-effort agar round berikutnya hemat (cap ukuran).
    try:
        if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
            d = _load_file()
            d[key] = [exp, value]
            if len(d) > 500:
                # buang yang paling kadaluarsa dulu
                for k in sorted(d, key=lambda k: float(d[k][0]) if isinstance(d[k], list) else 0)[: len(d) - 500]:
                    d.pop(k, None)
            _save_file(d)
    except Exception:
        pass

def clear():
    with _lock:
        _store.clear()
    try:
        if os.path.exists(_FILE):
            os.remove(_FILE)
    except Exception:
        pass
