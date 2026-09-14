"""Collector DexScreener (gratis, tanpa API key).
Docs: https://docs.dexscreener.com/api/reference
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import cache as _cache
from . import limits as _limits
from . import meter as _meter

log = logging.getLogger(__name__)

BASE = "https://api.dexscreener.com"
TIMEOUT = 15
RETRIES = 2

def _get(path: str, retries: int = RETRIES) -> Any:
    if not _meter.allow("dexscreener"):
        raise RuntimeError("budget dexscreener habis (circuit breaker)")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with _limits.guard("dexscreener"):
                _meter.count("dexscreener")
                r = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            if attempt >= retries:
                break
            # Backoff + jitter di LUAR semaphore (guard sudah lepas) agar tak
            # menahan worker ThreadPool lain selama tidur.
            import random as _r
            time.sleep(1.5 * (attempt + 1) + _r.uniform(0, 0.5))
    log.error("dexscreener %s gagal setelah retry: %s", path, str(last)[:160])
    raise last  # type: ignore[misc]

def get_token_pairs(chain: str, token_address: str) -> list[dict]:
    """GET /latest/dex/tokens/{tokenAddress} -> list pairs (lintas chain)."""
    addr = (token_address or "").strip()
    ch = (chain or "any").strip() or "any"
    # H1: cache key WAJIB menyertakan chain — address EVM yang sama bisa
    # hidup di base dan bsc sekaligus; key tanpa chain = data base dipakai
    # untuk bsc (tabrakan lintas chain).
    key = f"pairs:{ch}:{addr}"
    hit = _cache.get(key, 60)
    if hit is not None:
        return hit
    data = _get(f"/latest/dex/tokens/{addr}")
    pairs = data.get("pairs") or []
    if chain and chain != "any":
        pairs = [p for p in pairs if p.get("chainId") == chain]
    _cache.put(key, pairs, 60)
    return pairs

def get_pair(chain: str, pair_address: str) -> dict | None:
    data = _get(f"/latest/dex/pairs/{chain}/{pair_address}")
    pairs = data.get("pairs") or data.get("pair") or []
    if isinstance(pairs, dict):
        return pairs
    return pairs[0] if pairs else None

def search_pairs(query: str) -> list[dict]:
    from urllib.parse import quote
    data = _get(f"/latest/dex/search?q={quote(query, safe='')}")
    return data.get("pairs") or []

def get_top_boosts() -> list[dict]:
    """Token dengan boost teratas — bagus untuk universe awal."""
    hit = _cache.get("boosts", 120)
    if hit is not None:
        return hit
    out = _get("/token-boosts/top/v1")
    _cache.put("boosts", out, 120)
    return out

def get_latest_boosts() -> list[dict]:
    """Boost terbaru — rotasi cepat, bahan sniper. TTL pendek (60 dtk)."""
    hit = _cache.get("boosts_latest", 60)
    if hit is not None:
        return hit
    out = _get("/token-boosts/latest/v1")
    _cache.put("boosts_latest", out, 60)
    return out

def pick_best_pair(pairs: list[dict]) -> dict | None:
    """Pilih pair paling likuid sebagai representasi token."""
    if not pairs:
        return None
    def liq(p: dict) -> float:
        try:
            return float((p.get("liquidity") or {}).get("usd") or 0)
        except Exception:
            return 0.0
    return sorted(pairs, key=liq, reverse=True)[0]


CHART_BASE = "https://io.dexscreener.com"


def get_bars(chain: str, pair_addr: str, start_ms: int, end_ms: int,
             res: str = "5") -> list[dict]:
    """Ambil bar histori chart DexScreener (endpoint UI, best-effort).

    Alasan ada: GeckoTerminal menghapus pool token mati, tapi chart
    DexScreener sering masih menyimpan histori pair mati — satu-satunya
    cara menjawab MAE/MFE posisi lama tanpa menunggu data baru.
    Return candle terurut naik [{ts,o,h,l,c,v}] (ts = epoch detik).
    Gagal/berubah format -> [] (jujur, bukan karangan).
    """
    chain = (chain or "").strip()
    pair_addr = (pair_addr or "").strip()
    if not chain or not pair_addr or start_ms <= 0 or end_ms <= start_ms:
        return []
    try:
        import random as _r
        url = (f"{CHART_BASE}/u/chart/bars/{chain}/{pair_addr}"
               f"?res={res}&from={int(start_ms)}&to={int(end_ms)}&cb={_r.randint(1, 999999)}")
        r = requests.get(url, timeout=TIMEOUT,
                         headers={"Accept": "application/json",
                                  "Referer": "https://dexscreener.com/",
                                  "User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.debug("dexscreener bars gagal: %s", str(e)[:160])
        return []
    raw = []
    try:
        if isinstance(data, dict):
            raw = data.get("bars") or data.get("data") or []
        elif isinstance(data, list):
            raw = data
    except Exception:
        return []
    out = []
    for b in raw or []:
        try:
            if isinstance(b, dict):
                t = int(b.get("t", b.get("ts", b.get("time", 0))))
                o, h, lo, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
                v = float(b.get("v", b.get("volume", 0)) or 0)
            elif isinstance(b, (list, tuple)) and len(b) >= 6:
                t, o, h, lo, c, v = int(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5])
            else:
                continue
            if t > 10_000_000_000:  # ms -> detik
                t //= 1000
            if o <= 0 or h <= 0 or lo <= 0 or c <= 0:
                continue
            out.append({"ts": t, "o": o, "h": h, "l": lo, "c": c, "v": v})
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["ts"])
    return out
