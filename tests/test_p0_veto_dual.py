import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.config import load_config
from mmp.engine import gate as gt
from mmp.engine.signal import _dual_check, generate

CFG = {
    "signal": {"min_confidence": 85, "require_smart_money": True, "require_kol_or_sm": True},
    "tiers": {"tier2_min": 75, "tier2_size_pct": 0.5, "tier2_require_dual_source": True, "dual_max_divergence": 3.0},
    "risk": {"veto_on_blind": False},
}


def _ideal(chain="solana"):
    return {
        'chainId': chain, 'dexId': 'raydium', 'pairAddress': 'P', 'pairCreatedAt': 1000000000000,
        'baseToken': {'address': 'MINT', 'symbol': 'IDEAL', 'name': 'Ideal'}, 'priceUsd': '1.0',
        'liquidity': {'usd': 200000}, 'volume': {'h24': 500000, 'h1': 20000},
        'txns': {'h24': {'buys': 330, 'sells': 270}}, 'priceChange': {'h1': 5, 'h24': 50},
        'marketCap': 2000000, 'fdv': 2000000, 'url': 'https://x',
    }


def test_permissive_never_overrides_veto():
    v, reason, _, tier = gt.decide(["VETO: LIQ_TOO_LOW"], 90.0, CFG, permissive=True)
    assert v == "REJECT" and tier == 0 and "VETO" in reason
    v2, _, _, tier2 = gt.decide([], 90.0, CFG, permissive=True)
    assert v2 == "PASS" and tier2 == 1, "tanpa veto, permissive tetap PASS"


def test_permissive_end_to_end_with_honeypot():
    cfg = load_config()
    s = generate(
        _ideal("bsc"), cfg, permissive=True,
        enrichment={"source_honeypot_is": True, "buy_tax": 99.0, "sell_tax": 99.0, "labels": ["honeypot"]},
    )
    assert s.verdict == "REJECT" and any("honeypot" in x.lower() for x in s.vetoes)


def test_dual_missing_side_is_not_agree():
    ok, note = _dual_check(
        _ideal(), {"mint_renounced": True, "holders": 5000, "top10_pct": 10.0}, CFG
    )
    assert ok is False and "verifikasi" in note, "tanpa angka Birdeye = tak bisa diverifikasi"
    ok2, _ = _dual_check(_ideal(), {"mint_renounced": True, "holders": 5000}, CFG)
    assert ok2 is False
    ok3, _ = _dual_check(
        _ideal(),
        {"mint_renounced": True, "holders": 5000, "birdeye_mcap": 2000000, "birdeye_liq": 200000},
        CFG,
    )
    assert ok3 is True
