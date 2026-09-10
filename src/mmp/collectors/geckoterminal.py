"""GeckoTerminal collector (EVM gratis, tanpa API key untuk endpoint publik).
Dipakai sebagai universe fallback EVM + cross-check likuiditas/volume.
Docs: https://api.geckoterminal.com/
"""
from __future__ import annotations

import logging

import requests

from . import cache as _cache
from . import limits as _limits
from . import meter as _meter

log = logging.getLogger(__name__)

BASE = "https://api.geckoterminal.com/api/v2"
TIMEOUT = 15
NETWORKS = {"ethereum": "eth", "bsc": "bsc", "base": "base", "arbitrum": "arbitrum", "solana": "solana"}

def _get(path: str):
    if not _meter.allow("geckoterminal"):
        raise RuntimeError("budget geckoterminal habis (circuit breaker)")
    with _limits.guard("geckoterminal"):
        _meter.count("geckoterminal")
        r = requests.get(f"{BASE}{path}", timeout=TIMEOUT, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()

def get_top_pools(chain: str, limit: int = 10) -> list[dict]:
    """Top pools per network. Gagal (rate-limit/offline) -> []."""
    net = NETWORKS.get(chain, chain)
    key = f"gecko:top:{net}"
    hit = _cache.get(key, 300)
    if hit is not None:
        return hit[:limit]
    try:
        data = _get(f"/networks/{net}/pools?page=1")
        out = (data.get("data") or [])[:limit]
        _cache.put(key, out, 300)
        return out
    except Exception as e:
        log.debug("geckoterminal %s gagal: %s", chain, str(e)[:160])
        return []

def get_token_pools(chain: str, address: str, limit: int = 5) -> list[dict]:
    net = NETWORKS.get(chain, chain)
    try:
        data = _get(f"/networks/{net}/tokens/{address}/pools?page=1")
        return (data.get("data") or [])[:limit]
    except Exception as e:
        log.debug("geckoterminal token pools gagal: %s", str(e)[:160])
        return []

def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def _base_address(pool: dict) -> str:
    """Ekstrak contract address base token dari relationships (format 'chain_0x...').
    Kosong bila tak ada — pemanggil WAJIB menandai no-tax, bukan mengarang.
    """
    try:
        rel = (pool.get("relationships") or {}).get("baseToken", {}).get("data", {})
        rid = str(rel.get("id") or "")
        if "_" in rid:
            return rid.split("_", 1)[1]
        if rid.startswith("0x"):
            return rid
    except Exception:
        pass
    return ""


def pool_to_pair(pool: dict, chain: str) -> dict:
    """Normalisasi pool GeckoTerminal -> struktur pair ala DexScreener (subset dipakai MMP).
    JUJUR: baseToken.address bisa kosong (API top-pools tak selalu sertakan
    relationships) -> downstream honeypot.is tak bisa jalan -> tandai
    no_tax_addr=True agar tak diharapkan PASS (fail-closed, bukan vonis).
    """
    a = pool.get("attributes") or {}
    addr = a.get("address", "")
    price = _f(a.get("base_token_price_usd"))
    liq = _f(a.get("reserve_in_usd"))
    vol = (a.get("volume_usd") or {})
    tx = (a.get("transactions") or {})
    h24b = ((tx.get("h24") or {}).get("buys")) or 0
    h24s = ((tx.get("h24") or {}).get("sells")) or 0
    chg = (a.get("price_change_percentage") or {})
    base_addr = _base_address(pool)
    return {
        "chainId": chain, "dexId": a.get("dex_id", "gecko"), "pairAddress": addr,
        "baseToken": {"address": base_addr, "symbol": a.get("name", "?").split("/")[0].strip(), "name": a.get("name", "?")},
        "priceUsd": str(price), "liquidity": {"usd": liq},
        "volume": {"h24": _f(vol.get("h24")), "h1": _f(vol.get("h1"))},
        "txns": {"h24": {"buys": int(h24b or 0), "sells": int(h24s or 0)}},
        "priceChange": {"h1": _f((chg.get("h1"))), "h24": _f((chg.get("h24")))},
        "marketCap": _f(a.get("market_cap_usd")), "fdv": _f(a.get("fdv_usd")),
        "url": f"https://www.geckoterminal.com/{NETWORKS.get(chain, chain)}/pools/{addr}",
        "source": "geckoterminal-no-tax" if not base_addr else "geckoterminal",
        "no_tax_addr": not bool(base_addr),
    }

def universe_fallback(cfg: dict, per_chain: int = 5) -> list[dict]:
    """Pool EVM teratas sebagai fallback bila boosts DexScreener minim EVM."""
    if not (cfg.get("geckoterminal") or {}).get("enabled", True):
        return []
    out: list[dict] = []
    for chain in (cfg.get("chains") or {}).get("enabled", []):
        if chain == "solana":
            continue  # Solana prioritas via DexScreener+Helius
        for p in get_top_pools(chain, per_chain):
            try:
                out.append(pool_to_pair(p, chain))
            except Exception:
                continue
    return out
