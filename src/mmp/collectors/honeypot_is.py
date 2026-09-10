"""honeypot.is collector (EVM gratis, tanpa API key).
Mengisi 3 field yang selama ini selalu kosong di jalur EVM:
buy_tax, sell_tax, dan label honeypot -> veto otomatis via risk.py.
Chain: ethereum=1, bsc=56, base=8453, arbitrum=42161.
Rate-limit ketat -> semua failure = {} (graceful).
Docs: https://honeypot.is/
"""
from __future__ import annotations

import logging

import requests

from . import limits as _limits
from . import meter as _meter

log = logging.getLogger(__name__)

BASE = "https://api.honeypot.is/v2"
TIMEOUT = 15
CHAIN_IDS = {"ethereum": 1, "bsc": 56, "base": 8453, "arbitrum": 42161}

def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def check(chain: str, address: str) -> dict:
    cid = CHAIN_IDS.get(chain)
    if not cid or not address:
        return {}
    if not _meter.allow("honeypot_is"):
        return {}
    params: dict[str, str | int] = {"address": address, "chainID": cid}
    try:
        if not _meter.allow("honeypot_is"):
            return {}
        with _limits.guard("honeypot_is"):
            _meter.count("honeypot_is")
            r = requests.get(f"{BASE}/IsHoneypot", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json() or {}
    except Exception as e:
        log.debug("honeypot.is %s gagal: %s", chain, str(e)[:160])
        return {}

def build_enrichment(chain: str, address: str) -> dict:
    """Mapping ke kunci enrichment risk.py. Gagal -> {}."""
    if chain == "solana":
        return {}  # Solana via Helius, bukan sini
    d = check(chain, address)
    if not d:
        return {}
    out: dict = {"source_honeypot_is": True}
    bt, st = _f(d.get("buyTax")), _f(d.get("sellTax"))
    if bt is not None:
        out["buy_tax"] = round(bt, 2)
    if st is not None:
        out["sell_tax"] = round(st, 2)
    if d.get("isHoneypot"):
        out.setdefault("labels", []).append("honeypot")
    return out
