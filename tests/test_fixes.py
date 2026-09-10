import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sqlite3
from mmp.collectors import helius as hel
from mmp.collectors import dexscreener as dex
from mmp.collectors import universe as uni
from mmp.storage import paper as pstore
from mmp.backtest.engine import settle
from mmp.risk.position import build_plan

def _boom(*a, **k):
    raise RuntimeError("rpc down")

def test_helius_total_failure_returns_empty(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "dummy")
    monkeypatch.setattr(hel, "rpc", _boom)
    assert hel.build_enrichment("MINT", {}) == {}, "gagal total harus {}, bukan mint_renounced palsu"
    assert hel.get_top_holders("MINT") == []

def test_helius_resolves_owners_not_accounts(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "dummy")
    def fake_rpc(method, params, timeout=15):
        if method == "getTokenSupply":
            return {"value": {"amount": "1000000", "decimals": 6}}
        if method == "getAccountInfo":
            return {"value": {"data": {"parsed": {"info": {"mintAuthority": None, "freezeAuthority": None}}}}}
        if method == "getTokenLargestAccounts":
            return {"value": [{"address": "ATA1", "amount": "400000"}, {"address": "ATA2", "amount": "100000"}]}
        if method == "getMultipleAccounts":
            return {"value": [
                {"data": {"parsed": {"info": {"owner": "WALLET_A"}}}},
                {"data": {"parsed": {"info": {"owner": "WALLET_B"}}}},
            ]}
        raise AssertionError(method)
    monkeypatch.setattr(hel, "rpc", fake_rpc)
    en = hel.build_enrichment("MINT", {})
    assert en["holder_accounts"] == ["WALLET_A", "WALLET_B"], "harus owner, bukan ATA"
    assert en["top10_pct"] == 50.0 and en["mint_renounced"] is True

def test_owners_failure_is_fail_closed(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "dummy")
    monkeypatch.setattr(hel, "rpc", _boom)
    assert hel.get_accounts_owners(["ATA1"]) == {}

def test_paper_dedup():
    con = sqlite3.connect(":memory:")
    pstore.init(con)
    sig = {"db_id": 1, "symbol": "F", "chain": "solana", "token_address": "M",
           "pair_address": "P", "price_usd": 10.0, "plan": {"stop_loss": 8.5, "take_profit": 13.0}}
    assert pstore.has_open(con, "P") is False
    pstore.open_from_signal(con, sig)
    assert pstore.has_open(con, "P") is True
    assert pstore.has_open(con, "LAIN") is False

def test_settle_timeout():
    r = settle(100, 110, 15, 30, timeout_hit=True)
    assert r == {"status": "TIMEOUT", "pnl_pct": 10.0}
    assert settle(100, 110, 15, 30)["status"] == "OPEN"

def test_position_plan_honest_on_zero_entry():
    cfg = {"position": {"default_stop_loss_pct": 15.0, "default_take_profit_pct": 30.0,
                        "min_reward_risk": 1.5, "max_risk_per_trade_pct": 1.0}}
    assert build_plan(0, cfg)["expectancy_ok"] is False
    assert build_plan(100.0, cfg)["expectancy_ok"] is True

def test_dexscreener_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"pairs": []}
    def flaky(url, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("down")
        return Resp()
    monkeypatch.setattr(dex.requests, "get", flaky)
    assert dex._get("/x") == {"pairs": []} and calls["n"] == 2

def test_universe_survives_pair_failures(monkeypatch):
    monkeypatch.setattr(dex, "get_token_pairs", _boom)
    cfg = {"chains": {"enabled": ["solana"], "priority": ["solana"], "per_chain_limit": 5}}
    boosts = [{"tokenAddress": "A", "chainId": "solana"}]
    assert uni.universe_from_boosts(boosts, cfg) == []
