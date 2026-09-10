import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sqlite3
from mmp.engine import gate as gt
from mmp.engine.signal import generate
from mmp.config import load_config
from mmp.storage import paper as pstore
from mmp.notifiers.telegram import format_signal

CFG = {"signal": {"min_confidence": 85, "require_smart_money": True, "require_kol_or_sm": True},
       "tiers": {"tier2_min": 75, "tier2_size_pct": 0.5, "tier2_require_dual_source": True}}

def test_gate_tiers():
    v, _, th, tier = gt.decide([], 90.0, CFG)
    assert (v, tier, th) == ("PASS", 1, 85)
    v, _, th, tier = gt.decide([], 80.0, CFG, dual_source=True)
    assert (v, tier, th) == ("PASS", 2, 75)
    v, _, _, tier = gt.decide([], 80.0, CFG, dual_source=False)
    assert (v, tier) == ("REJECT", 0)
    v, _, _, tier = gt.decide([], 70.0, CFG, dual_source=True)
    assert (v, tier) == ("REJECT", 0)
    v, _, _, tier = gt.decide(["VETO: X"], 95.0, CFG, dual_source=True)
    assert (v, tier) == ("REJECT", 0), "veto membunuh semua tier"

def _ideal():
    return {'chainId': 'solana', 'dexId': 'raydium', 'pairAddress': 'P', 'pairCreatedAt': 1000000000000,
            'baseToken': {'address': 'MINT', 'symbol': 'IDEAL', 'name': 'Ideal'}, 'priceUsd': '1.0',
            'liquidity': {'usd': 200000}, 'volume': {'h24': 500000, 'h1': 20000},
            'txns': {'h24': {'buys': 330, 'sells': 270}}, 'priceChange': {'h1': 5, 'h24': 50},
            'marketCap': 2000000, 'fdv': 2000000, 'url': 'https://x'}

def test_generate_tier2_needs_dual_source():
    cfg = load_config()
    he = {'top10_pct': 15.0, 'top_holder_pct': 5.0, 'mint_renounced': True,
          'holder_accounts': ['A1'], 'holders': 5000}  # Helius + Birdeye
    s = generate(_ideal(), cfg, helius_enrich=he, trusted_overlap=2)
    assert (s.verdict, s.tier) == ("PASS", 2), s.reason
    he_nobirdeye = {k: v for k, v in he.items() if k != 'holders'}
    s2 = generate(_ideal(), cfg, helius_enrich=he_nobirdeye, trusted_overlap=2)
    assert (s2.verdict, s2.tier) == ("REJECT", 0), "tanpa Birdeye tak boleh TIER-2"

def test_paper_stores_tier():
    con = sqlite3.connect(":memory:")
    pstore.init(con)
    sig = {"db_id": 9, "symbol": "F", "chain": "solana", "token_address": "M",
           "pair_address": "P", "price_usd": 10.0, "tier": 2,
           "plan": {"stop_loss": 8.5, "take_profit": 13.0}}
    pid = pstore.open_from_signal(con, sig, 0.5)
    row = con.execute("SELECT tier, risk_pct FROM paper_positions WHERE id=?", (pid,)).fetchone()
    assert tuple(row) == (2, 0.5)

def test_telegram_tier_badge():
    d = {"verdict": "PASS", "tier": 2, "symbol": "F", "chain": "solana", "confidence": 80,
         "threshold": 75, "price_usd": 1.0, "dex": "raydium", "reason": "TIER-2",
         "vetoes": [], "scores": {}, "plan": {}, "meta": {}}
    t = format_signal(d)
    assert "TIER-2" in t and "🔶" in t
