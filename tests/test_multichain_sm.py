import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mmp.collectors import universe as uni
from mmp.analyzers import smart_money_auto as sma

def _pair(**kw):
    base = {"chainId": "solana", "liquidity": {"usd": 100000}, "volume": {"h24": 300000},
            "txns": {"h24": {"buys": 300, "sells": 250}}, "baseToken": {"address": "X", "symbol": "T"}}
    base.update(kw)
    return base

def test_universe_solana_priority():
    cfg = {"chains": {"enabled": ["solana", "base"], "priority": ["solana", "base"], "per_chain_limit": 10}}
    pairs = [_pair(chainId="base"), _pair(chainId="solana"), _pair(chainId="bsc")]
    out = uni.filter_and_sort(pairs, cfg)
    assert [p["chainId"] for p in out] == ["solana", "base"], "solana harus duluan, bsc terfilter"

def test_auto_sm_capped_and_sensible():
    cfg = {"smart_money_auto": {"max_auto_score": 85, "healthy_buy_ratio_min": 0.5,
                                "healthy_buy_ratio_max": 0.7, "max_top_holder_pct": 15.0}}
    s, _, meta, _ = sma.discover(_pair(), {}, cfg)
    assert 0 < s <= 85
    assert meta["helius_used"] is False

def test_auto_sm_penalize_concentration():
    cfg = {"smart_money_auto": {"max_auto_score": 85, "healthy_buy_ratio_min": 0.5,
                                "healthy_buy_ratio_max": 0.7, "max_top_holder_pct": 15.0}}
    s1, _, _, _ = sma.discover(_pair(), {"top10_pct": 10, "top_holder_pct": 3, "mint_renounced": True}, cfg)
    s2, _, _, _ = sma.discover(_pair(), {"top10_pct": 60, "top_holder_pct": 30, "mint_renounced": False}, cfg)
    assert s1 > s2, "distribusi pekat harus skor lebih rendah"
