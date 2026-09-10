"""Multi-chain universe builder. Solana prioritas, EVM mengikuti.
DexScreener chainId: solana, ethereum, bsc, base, arbitrum.
"""
from __future__ import annotations
import logging
from . import dexscreener as dex

log = logging.getLogger(__name__)

PRIORITY_DEFAULT = ["solana", "ethereum", "bsc", "base", "arbitrum"]

def chain_priority(chain: str, cfg: dict) -> int:
    prio: list[str] = (cfg.get("chains") or {}).get("priority", PRIORITY_DEFAULT)
    try:
        return prio.index(chain)
    except ValueError:
        return 99

def filter_and_sort(pairs: list[dict], cfg: dict) -> list[dict]:
    enabled: list[str] = (cfg.get("chains") or {}).get("enabled", ["solana"])
    out = [p for p in pairs if (p.get("chainId") in enabled)]
    out.sort(key=lambda p: (chain_priority(p.get("chainId", ""), cfg), -(float(((p.get("liquidity") or {}).get("usd")) or 0))))
    return out

def universe_from_boosts(boosts: list[dict], cfg: dict, limit_per_chain: int | None = None) -> list[dict]:
    """Ambil boosts -> resolve ke best pair -> filter multi-chain -> sort prioritas."""
    per_chain: int = limit_per_chain or int((cfg.get("chains") or {}).get("per_chain_limit", 10))
    enabled: list[str] = (cfg.get("chains") or {}).get("enabled", ["solana"])
    counts: dict[str, int] = {c: 0 for c in enabled}
    # sort boosts: solana dulu
    boosts_sorted = sorted(boosts, key=lambda b: chain_priority(b.get("chainId", "solana"), cfg))
    pairs: list[dict] = []
    for b in boosts_sorted:
        addr = b.get("tokenAddress")
        chain = b.get("chainId", "solana")
        if chain not in enabled or counts.get(chain, 0) >= per_chain:
            continue
        try:
            ps = dex.get_token_pairs(chain, addr)
            best = dex.pick_best_pair(ps)
            if best:
                pairs.append(best)
                counts[chain] = counts.get(chain, 0) + 1
        except Exception as e:
            log.debug("universe skip %s (%s): %s", addr, chain, str(e)[:160])
            continue
    return filter_and_sort(pairs, cfg)
