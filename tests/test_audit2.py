import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mmp.engine.signal import generate, _dual_check
from mmp.analyzers import risk as risk_an
from mmp.collectors import helius as hel
from mmp.collectors import prices as pxr
from mmp.config import load_config

def _ideal(chain="solana"):
    return {'chainId': chain, 'dexId': 'raydium', 'pairAddress': 'P', 'pairCreatedAt': 1000000000000,
            'baseToken': {'address': 'MINT', 'symbol': 'IDEAL', 'name': 'Ideal'}, 'priceUsd': '1.0',
            'liquidity': {'usd': 200000}, 'volume': {'h24': 500000, 'h1': 20000},
            'txns': {'h24': {'buys': 330, 'sells': 270}}, 'priceChange': {'h1': 5, 'h24': 50},
            'marketCap': 2000000, 'fdv': 2000000, 'url': 'https://x'}

def _he(**kw):
    d = {'top10_pct': 15.0, 'top_holder_pct': 5.0, 'mint_renounced': True,
         'holder_accounts': ['A1'], 'holders': 5000,
         'birdeye_mcap': 2100000, 'birdeye_liq': 190000}
    d.update(kw)
    return d

def test_dual_conflict_blocks_tier2():
    cfg = load_config()
    ok, note = _dual_check(_ideal(), _he(birdeye_mcap=20000000), cfg)
    assert ok is False and "konflik mcap" in note
    s = generate(_ideal(), cfg, helius_enrich=_he(birdeye_mcap=20000000), trusted_overlap=2)
    assert (s.verdict, s.tier) == ("REJECT", 0), "konflik antar-sumber = bukan dual"
    assert s.meta["dual"]["ok"] is False

def test_dual_consistent_passes_tier2():
    cfg = load_config()
    s = generate(_ideal(), cfg, helius_enrich=_he(), trusted_overlap=2)
    assert (s.verdict, s.tier) == ("PASS", 2)
    assert s.meta["data_grade"] == "COMPLETE"

def test_evm_tier2_via_honeypot_is():
    cfg = load_config()
    pair = _ideal("base")
    en = {"source_honeypot_is": True, "buy_tax": 2.0, "sell_tax": 3.0}
    ok, note = _dual_check(pair, en, cfg)
    assert ok is True, note
    s = generate(pair, cfg, enrichment=en)
    assert (s.verdict, s.tier) == ("PASS", 2), s.reason
    assert s.meta["data_grade"] == "COMPLETE"

def test_evm_honeypot_veto_and_blind_grade():
    cfg = load_config()
    pair = _ideal("bsc")
    s = generate(pair, cfg, enrichment={"source_honeypot_is": True, "buy_tax": 99.0,
                                        "sell_tax": 99.0, "labels": ["honeypot"]})
    assert s.verdict == "REJECT" and any("honeypot" in v.lower() for v in s.vetoes)
    g, missing = risk_an.data_grade(pair, {})
    assert g == "BLIND"
    g2, _ = risk_an.data_grade(_ideal(), {})
    assert g2 == "BLIND"

def test_freeze_authority_veto(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "dummy")
    def fake_rpc(method, params, timeout=15):
        if method == "getTokenSupply":
            return {"value": {"amount": "1000000", "decimals": 6}}
        if method == "getAccountInfo":
            return {"value": {"data": {"parsed": {"info": {"mintAuthority": None, "freezeAuthority": "FZ"}}}}}
        if method == "getTokenLargestAccounts":
            return {"value": []}
        if method == "getMultipleAccounts":
            return {"value": []}
        raise AssertionError(method)
    monkeypatch.setattr(hel, "rpc", fake_rpc)
    en = hel.build_enrichment("MINT", {})
    assert "freezable-risk" in en["labels"]
    cfg = load_config()
    vetoes = risk_an.check_hard_veto(_ideal(), cfg, en)
    assert any("freezable" in v.lower() for v in vetoes)

def test_veto_on_blind_opt_in():
    cfg = load_config()
    cfg["risk"] = dict(cfg["risk"], veto_on_blind=True)
    s = generate(_ideal(), cfg)
    assert any("DATA_BLIND" in v for v in s.vetoes)
    cfg["risk"]["veto_on_blind"] = False
    s2 = generate(_ideal(), cfg)
    assert not any("DATA_BLIND" in v for v in s2.vetoes)

def test_price_fallback_chain(monkeypatch):
    import mmp.collectors.dexscreener as dexmod
    import mmp.collectors.geckoterminal as gmod
    monkeypatch.setattr(dexmod, "get_token_pairs", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dex down")))
    monkeypatch.setattr(dexmod, "get_pair", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dex down")))
    monkeypatch.setattr(gmod, "get_token_pools",
                        lambda c, a, l=1: [{"attributes": {"address": "0xp", "name": "F / USDC",
                                                           "base_token_price_usd": "2.5", "reserve_in_usd": "1000",
                                                           "volume_usd": {}, "transactions": {},
                                                           "price_change_percentage": {}}}])
    px, src = pxr.resolve_price("base", "0xtoken", "0xpair")
    assert (px, src) == (2.5, "geckoterminal")
    px2, src2 = pxr.resolve_price("base", "", "")
    assert (px2, src2) == (0.0, "none")
