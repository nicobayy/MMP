"""Multi-chain universe builder. Solana prioritas, EVM mengikuti.
DexScreener chainId: solana, ethereum, bsc, base, arbitrum.
Resolve pair paralel (satu sumber: DexScreener) via ThreadPoolExecutor;
perakitan limit-per-chain tetap sekuensial agar deterministik.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

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

def _resolve_boost(item: tuple[str, str]) -> tuple[str, dict | None]:
    """Resolve 1 boost -> (chain, best pair|None). Murni network, tanpa state."""
    chain, addr = item
    try:
        return chain, dex.pick_best_pair(dex.get_token_pairs(chain, addr))
    except Exception as e:
        log.debug("universe skip %s (%s): %s", addr, chain, str(e)[:160])
        return chain, None

def universe_from_boosts(boosts: list[dict], cfg: dict, limit_per_chain: int | None = None) -> list[dict]:
    """Ambil boosts -> resolve ke best pair -> filter multi-chain -> sort prioritas."""
    per_chain: int = limit_per_chain or int((cfg.get("chains") or {}).get("per_chain_limit", 10))
    enabled: list[str] = (cfg.get("chains") or {}).get("enabled", ["solana"])
    counts: dict[str, int] = {c: 0 for c in enabled}
    # sort boosts: solana dulu
    boosts_sorted = sorted(boosts, key=lambda b: chain_priority(b.get("chainId", "solana"), cfg))
    wanted: list[tuple[str, str]] = []
    pre: dict[str, int] = {c: 0 for c in enabled}
    for b in boosts_sorted:
        addr = b.get("tokenAddress")
        chain = b.get("chainId", "solana")
        # Batasi SEBELUM resolve agar tak bakar API untuk kandidat yang pasti dibuang.
        if addr and chain in enabled and pre.get(chain, 0) < per_chain:
            wanted.append((chain, addr))
            pre[chain] = pre.get(chain, 0) + 1
    workers = int((cfg.get("concurrency") or {}).get("universe_workers", 4))
    if workers > 1 and len(wanted) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            resolved = list(ex.map(_resolve_boost, wanted))
    else:
        resolved = [_resolve_boost(w) for w in wanted]
    pairs: list[dict] = []
    for chain, best in resolved:
        if best and counts.get(chain, 0) < per_chain:
            pairs.append(best)
            counts[chain] = counts.get(chain, 0) + 1
    return filter_and_sort(pairs, cfg)
