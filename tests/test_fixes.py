import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sqlite3

from mmp.backtest.engine import settle
from mmp.collectors import dexscreener as dex
from mmp.collectors import helius as hel
from mmp.collectors import universe as uni
from mmp.risk.position import build_plan
from mmp.storage import paper as pstore


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

def test_paper_reentry_cooldown():
    con = sqlite3.connect(":memory:")
    pstore.init(con)
    assert pstore.recently_closed(con, "solana", "M", "P", 12.0) == (False, None)
    pid = pstore.open_from_signal(con, {"db_id": 1, "symbol": "F", "chain": "solana",
        "token_address": "M", "pair_address": "P", "price_usd": 10.0,
        "plan": {"stop_loss": 8.5, "take_profit": 13.0}})
    pstore.close_position(con, pid, 11.0, 10.0, "TP")
    dup, _when = pstore.recently_closed(con, "solana", "M", "P2", 12.0)
    assert dup is True, "token sama pair beda tetap diblokir"
    dup2, _ = pstore.recently_closed(con, "solana", "LAIN", "P3", 12.0)
    assert dup2 is False
    dup3, _ = pstore.recently_closed(con, "solana", "M", "P", 0)
    assert dup3 is False, "cooldown 0 = mati"

def test_settle_spot_closes_despite_stale_candles(monkeypatch):
    """Regresi: candle basi tanpa hit + spot jebol SL -> wajib SL, bukan OPEN.

    Kasus nyata: CATAI/Stunk sniper entry lalu dump -22%, posisi stuck OPEN
    karena replay di atas candle basi me-return OPEN dan cek spot di-skip.
    """
    import importlib.util
    from pathlib import Path as _P
    spec = importlib.util.spec_from_file_location(
        "paper_mod", str(_P(__file__).resolve().parents[1] / "scripts" / "paper.py"))
    paper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paper)
    con = sqlite3.connect(":memory:")
    from mmp.storage import candles as cstore
    cstore.init(con)
    now = int(__import__("time").time())
    # candle basi (2 jam lalu): open==close==entry, tak sentuh SL/TP
    cstore.upsert_candles(con, "solana", "POOL1", "hour",
                          [{"ts": now - 7200, "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": 1.0}])
    monkeypatch.setattr(paper.ohlcv_mod, "resolve_pool", lambda c, t: "POOL1")
    monkeypatch.setattr(paper.ohlcv_mod, "fetch", lambda *a, **k: [])
    monkeypatch.setattr(paper.pxr, "resolve_price", lambda c, t, p="": (85.0, "dexscreener"))
    from datetime import datetime, timezone
    opened = datetime.fromtimestamp(now - 3600, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    o = {"chain": "solana", "token": "M", "pair_addr": "P", "entry": 100.0,
         "sl": 94.0, "tp": 115.0, "opened_ts": opened}
    cfg = {"position": {"default_stop_loss_pct": 6.0, "default_take_profit_pct": 15.0},
           "backtest": {"replay_limit": 500}}
    r = paper.settle_position(o, cfg, 6.0, 1.0, 0.3, con)
    assert r["status"] == "SL", f"spot -15% wajib SL, dapat {r}"

def test_settle_end_ts_bounds_replay(monkeypatch):
    """Candle setelah close aktual wajib diabaikan (perbandingan profil adil)."""
    import importlib.util
    from pathlib import Path as _P
    spec = importlib.util.spec_from_file_location(
        "paper_mod2", str(_P(__file__).resolve().parents[1] / "scripts" / "paper.py"))
    paper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paper)
    con = sqlite3.connect(":memory:")
    from mmp.storage import candles as cstore
    cstore.init(con)
    now = int(__import__("time").time())
    cstore.upsert_candles(con, "solana", "POOL2", "hour", [
        {"ts": now - 7200, "o": 100.0, "h": 110.0, "l": 99.0, "c": 108.0, "v": 1.0},
        {"ts": now - 3600, "o": 108.0, "h": 109.0, "l": 50.0, "c": 60.0, "v": 1.0},
    ])
    monkeypatch.setattr(paper.ohlcv_mod, "resolve_pool", lambda c, t: "POOL2")
    monkeypatch.setattr(paper.ohlcv_mod, "fetch", lambda *a, **k: [])
    monkeypatch.setattr(paper.pxr, "resolve_price", lambda c, t, p="": (100.0, "dexscreener"))
    from datetime import datetime, timezone
    opened = datetime.fromtimestamp(now - 8000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    o = {"chain": "solana", "token": "M", "pair_addr": "P", "entry": 100.0,
         "sl": 94.0, "tp": 115.0, "opened_ts": opened}
    cfg = {"position": {"default_stop_loss_pct": 6.0, "default_take_profit_pct": 15.0},
           "backtest": {"replay_limit": 500}}
    r_bound = paper.settle_position(o, cfg, 6.0, 1.0, 0.3, con, end_ts=now - 5000)
    assert r_bound["status"] == "OPEN", f"candle dump setelah bound wajib diabaikan, dapat {r_bound}"
    r_full = paper.settle_position(o, cfg, 6.0, 1.0, 0.3, con)
    assert r_full["status"] == "SL", f"tanpa bound dump terlihat -> SL, dapat {r_full}"

def test_latest_boosts_endpoint_and_cache(monkeypatch):
    from mmp.collectors import cache as _cache
    from mmp.collectors import dexscreener as _dex
    _cache.clear()
    calls = {"n": 0}

    def fake_get(path, retries=2):
        calls["n"] += 1
        assert path == "/token-boosts/latest/v1"
        return [{"tokenAddress": "X", "chainId": "solana"}]
    monkeypatch.setattr(_dex, "_get", fake_get)
    assert _dex.get_latest_boosts() == [{"tokenAddress": "X", "chainId": "solana"}]
    assert _dex.get_latest_boosts() == [{"tokenAddress": "X", "chainId": "solana"}]
    assert calls["n"] == 1, "panggilan kedua wajib dari cache"

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

def test_paper_pool_recorded():
    con = sqlite3.connect(":memory:")
    pstore.init(con)
    pid = pstore.open_from_signal(con, {"db_id": 1, "symbol": "F", "chain": "solana",
        "token_address": "M", "pair_address": "P", "price_usd": 10.0,
        "plan": {"stop_loss": 8.5, "take_profit": 13.0}})
    pstore.set_pool(con, pid, "POOLX")
    row = con.execute("SELECT pool FROM paper_positions WHERE id=?", (pid,)).fetchone()
    assert row[0] == "POOLX"
    pstore.set_pool(con, pid, "LAIN")
    row = con.execute("SELECT pool FROM paper_positions WHERE id=?", (pid,)).fetchone()
    assert row[0] == "POOLX", "pool pertama menang (jangan timpa)"
