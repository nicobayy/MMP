"""Birdeye collector (Solana). Aktif hanya bila BIRDEYE_API_KEY ada.
Dipakai untuk cross-check: holder count, volume, price change, trades overview.
Semua failure -> {} (graceful, jangan bunuh scan).
Docs: https://docs.birdeye.so/
"""
from __future__ import annotations
import os
import requests

BASE = "https://public-api.birdeye.so"
TIMEOUT = 15

def api_key() -> str:
    return os.getenv("BIRDEYE_API_KEY", "").strip().strip('"').strip("'")

def has_key() -> bool:
    return bool(api_key())

def _get(path: str, params: dict | None = None):
    r = requests.get(f"{BASE}{path}", params=params or {},
                     headers={"X-API-KEY": api_key(), "accept": "application/json"},
                     timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def get_token_overview(mint: str) -> dict:
    try:
        return (_get("/defi/token_overview", {"address": mint}) or {}).get("data") or {}
    except Exception:
        return {}

def get_price(mint: str) -> float:
    try:
        return float((_get("/defi/price", {"address": mint}) or {}).get("data", {}).get("value") or 0)
    except Exception:
        return 0.0

def build_enrichment(mint: str) -> dict:
    """Mapping ke kunci enrichment risk.py. Tanpa key -> {}."""
    if not has_key() or not mint:
        return {}
    ov = get_token_overview(mint)
    if not ov:
        return {}
    out: dict = {"source_birdeye": True}
    try:
        if ov.get("holder") is not None:
            out["holders"] = int(ov["holder"])
        mc = float(ov.get("mc") or 0)
        liq = float(ov.get("liquidity") or 0)
        if mc:
            out["birdeye_mcap"] = mc
        if liq:
            out["birdeye_liq"] = liq
        v24 = (ov.get("v24hUSD") or ov.get("v24h") or 0)
        out["birdeye_vol24"] = float(v24 or 0)
    except Exception:
        pass
    return out
