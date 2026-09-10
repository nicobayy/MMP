"""Resolusi harga berlapis (redundancy): DexScreener -> GeckoTerminal -> Birdeye.
Satu sumber down tak lagi membutakan paper-settle & backtest.
Return (price, source). Gagal semua -> (0.0, "none").
"""
from __future__ import annotations

from . import birdeye as bir
from . import dexscreener as dex
from . import geckoterminal as gecko


def resolve_price(chain: str, token: str, pair_addr: str = "") -> tuple[float, str]:
    if token:
        try:
            pairs = dex.get_token_pairs(chain, token)
            best = dex.pick_best_pair(pairs) if pairs else None
            px = float((best or {}).get("priceUsd") or 0)
            if px:
                return px, "dexscreener"
        except Exception:
            pass
        try:
            pools = gecko.get_token_pools(chain, token, 1)
            if pools:
                px = float(gecko.pool_to_pair(pools[0], chain).get("priceUsd") or 0)
                if px:
                    return px, "geckoterminal"
        except Exception:
            pass
        if chain == "solana":
            try:
                px = bir.get_price(token)
                if px:
                    return px, "birdeye"
            except Exception:
                pass
    if pair_addr and chain:
        try:
            p = dex.get_pair(chain, pair_addr)
            px = float((p or {}).get("priceUsd") or 0)
            if px:
                return px, "dexscreener-pair"
        except Exception:
            pass
    return 0.0, "none"
