"""OHLCV historis via GeckoTerminal (gratis, semua network incl. Solana).
Endpoint: /networks/{net}/pools/{pool}/ohlcv/{timeframe}?aggregate=1&limit=N&currency=usd
Respons: data.attributes.ohlcv_list = [[ts, o, h, l, c, v], ...] (ts = epoch detik).

REALITY-CHECK: depth tier gratis terbatas (cek via scripts/ohlcv_check.py).
Repo muda -> belum ada histori PASS lama; pola utama = forward replay:
sinyal baru dicatat, candle diputar ke depan. BUKAN sulap data masa lalu.
"""
from __future__ import annotations

import logging

from . import geckoterminal as gecko

log = logging.getLogger(__name__)

TIMEFRAMES = ("minute", "hour", "day")

def fetch(chain: str, pool: str, timeframe: str = "hour", limit: int = 100) -> list[dict]:
    """Return candle terurut naik: [{ts, o, h, l, c, v}]. Gagal -> []."""
    net = gecko.NETWORKS.get(chain, chain)
    if timeframe not in TIMEFRAMES or not pool:
        return []
    limit = max(1, min(int(limit), 1000))
    try:
        data = gecko._get(f"/networks/{net}/pools/{pool}/ohlcv/{timeframe}"
                          f"?aggregate=1&limit={limit}&currency=usd")
        rows = ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    except Exception as e:
        log.debug("ohlcv %s/%s gagal: %s", chain, pool, str(e)[:160])
        return []
    out = []
    for r in rows:
        try:
            ts, o, h, low, c, v = r
            out.append({"ts": int(ts), "o": float(o), "h": float(h),
                        "l": float(low), "c": float(c), "v": float(v)})
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["ts"])
    return out

def resolve_pool(chain: str, token: str) -> str:
    """Pool address paling likuid untuk token (untuk OHLCV). Kosong bila tak ada."""
    try:
        pools = gecko.get_token_pools(chain, token, 5)
    except Exception:
        return ""
    best = ""
    best_liq = -1.0
    for p in pools:
        a = (p.get("attributes") or {})
        try:
            liq = float(a.get("reserve_in_usd") or 0)
        except (TypeError, ValueError):
            liq = 0.0
        if liq > best_liq:
            best_liq = liq
            best = a.get("address", "")
    return best

def depth(chain: str, pool: str) -> dict:
    """Lapor ketersediaan histori: {n_hour, oldest, newest}. Untuk ohlcv_check."""
    cs = fetch(chain, pool, "hour", 1000)
    if not cs:
        return {"n_hour": 0, "oldest": None, "newest": None}
    return {"n_hour": len(cs), "oldest": cs[0]["ts"], "newest": cs[-1]["ts"]}
