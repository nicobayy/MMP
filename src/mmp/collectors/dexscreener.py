"""Collector DexScreener (gratis, tanpa API key).
Docs: https://docs.dexscreener.com/api/reference
"""
from __future__ import annotations
import requests
import time
from typing import Any

BASE = "https://api.dexscreener.com"
TIMEOUT = 15
RETRIES = 2

def _get(path: str, retries: int = RETRIES) -> Any:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{BASE}{path}", timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]

def get_token_pairs(chain: str, token_address: str) -> list[dict]:
    """GET /latest/dex/tokens/{tokenAddress} -> list pairs (lintas chain)."""
    data = _get(f"/latest/dex/tokens/{token_address}")
    pairs = data.get("pairs") or []
    if chain and chain != "any":
        pairs = [p for p in pairs if p.get("chainId") == chain]
    return pairs

def get_pair(chain: str, pair_address: str) -> dict | None:
    data = _get(f"/latest/dex/pairs/{chain}/{pair_address}")
    pairs = data.get("pairs") or data.get("pair") or []
    if isinstance(pairs, dict):
        return pairs
    return pairs[0] if pairs else None

def search_pairs(query: str) -> list[dict]:
    data = _get(f"/latest/dex/search?q={query}")
    return data.get("pairs") or []

def get_top_boosts() -> list[dict]:
    """Token dengan boost teratas — bagus untuk universe awal."""
    return _get("/token-boosts/top/v1")

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
