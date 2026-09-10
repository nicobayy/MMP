import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.backtest.replay import bucket, calibrate, replay
from mmp.collectors import cache as _cache
from mmp.collectors import limits as _limits
from mmp.collectors import meter as _meter
from mmp.collectors import ohlcv
from mmp.collectors import universe as uni
from mmp.storage import candles as cstore


def test_cache_meter_thread_safe():
    _cache.clear()
    _meter.reset()
    def work(i):
        for j in range(50):
            _cache.put(f"k{i}-{j}", j)
            _meter.count("t")
    ts = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert _meter.summary() == {"t": 400}
    assert _cache.get("k3-7", 60) == 7
    _cache.clear()
    _meter.reset()


def test_limits_cap_concurrency():
    _limits.configure({"s": 2})
    cur = {"n": 0, "mx": 0}
    lock = threading.Lock()
    def work():
        with _limits.guard("s"):
            with lock:
                cur["n"] += 1
                cur["mx"] = max(cur["mx"], cur["n"])
            import time
            time.sleep(0.02)
            with lock:
                cur["n"] -= 1
    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert cur["mx"] <= 2, f"semaphore bocor: {cur['mx']}"
    _limits.configure({})


def test_universe_parallel_matches_sequential(monkeypatch):
    import mmp.collectors.dexscreener as dexmod
    def fake_pairs(chain, addr):
        return [{"chainId": chain, "pairAddress": f"P-{addr}",
                 "liquidity": {"usd": 1000 + len(addr)}}]
    monkeypatch.setattr(dexmod, "get_token_pairs", fake_pairs)
    cfg = {"chains": {"enabled": ["solana", "base"], "priority": ["solana", "base"], "per_chain_limit": 2},
           "concurrency": {"universe_workers": 4}}
    boosts = [{"tokenAddress": f"T{i}", "chainId": "solana" if i % 2 == 0 else "base"} for i in range(6)]
    par = uni.universe_from_boosts(boosts, cfg)
    cfg1 = {"chains": cfg["chains"], "concurrency": {"universe_workers": 1}}
    seq = uni.universe_from_boosts(boosts, cfg1)
    assert [p["pairAddress"] for p in par] == [p["pairAddress"] for p in seq]
    assert len(par) == 4, "limit 2 per chain x 2 chain"


def test_ohlcv_parse_and_resolve(monkeypatch):
    import mmp.collectors.geckoterminal as gmod
    monkeypatch.setattr(gmod, "_get", lambda path: {"data": {"attributes": {"ohlcv_list": [
        [1700000000, "1", "1.2", "0.9", "1.1", "100"],
        ["bad"],
        [1700003600, "1.1", "1.5", "1.0", "1.4", "200"],
    ]}}})
    cs = ohlcv.fetch("base", "0xp", "hour", 10)
    assert [c["ts"] for c in cs] == [1700000000, 1700003600] and cs[0]["h"] == 1.2
    assert ohlcv.fetch("base", "", "hour") == []
    assert ohlcv.fetch("base", "0xp", "week") == []
    monkeypatch.setattr(gmod, "get_token_pools", lambda c, a, lim=1: [
        {"attributes": {"address": "P1", "reserve_in_usd": "10"}},
        {"attributes": {"address": "P2", "reserve_in_usd": "99"}},
    ])
    assert ohlcv.resolve_pool("base", "0xt") == "P2"


def test_candles_store():
    con = sqlite3.connect(":memory:")
    cstore.init(con)
    rows = [{"ts": 1, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10},
            {"ts": 2, "o": 1.5, "h": 1.6, "l": 1.4, "c": 1.55, "v": 5},
            {"ts": "x", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]
    assert cstore.upsert_candles(con, "base", "P", "hour", rows) == 2
    got = cstore.get_candles(con, "base", "P", "hour", since=2)
    assert [c["ts"] for c in got] == [2]
    cov = cstore.coverage(con)
    assert cov[0]["n"] == 2


def _c(ts, o, h, low, c):
    return {"ts": ts, "o": o, "h": h, "l": low, "c": c, "v": 1}


def test_replay_tp_sl_order_and_mfe_mae():
    assert replay(0, 100, 15, 30, [])["status"] == "NO_DATA"
    r = replay(0, 100, 15, 30, [_c(0, 100, 105, 95, 102), _c(3600, 102, 140, 100, 130)])
    assert r["status"] == "TP" and r["pnl_pct"] == 30.0 and r["bars"] == 2
    assert r["mfe"] == 40.0 and r["mae"] == -5.0
    r2 = replay(0, 100, 15, 30, [_c(0, 100, 140, 50, 130)])
    assert r2["status"] == "SL", "TP+SL satu candle -> SL (konservatif)"
    r3 = replay(0, 100, 15, 30, [_c(0, 100, 110, 90, 105)], timeout_h=0)
    assert r3["status"] == "TIMEOUT" and r3["pnl_pct"] == 5.0
    r4 = replay(9999, 100, 15, 30, [_c(0, 100, 101, 99, 100)])
    assert r4["status"] == "NO_DATA", "candle sebelum entry tak dihitung"


def test_calibrate_buckets_and_tiers():
    rows = [
        {"conf": 82, "tier": 2, "status": "TP", "pnl_pct": 30, "mfe": 40, "mae": -5},
        {"conf": 84, "tier": 2, "status": "SL", "pnl_pct": -15, "mfe": 5, "mae": -20},
        {"conf": 90, "tier": 1, "status": "TP", "pnl_pct": 30, "mfe": 35, "mae": -2},
        {"conf": 50, "tier": 1, "status": "OPEN", "pnl_pct": 5, "mfe": 5, "mae": 0},
    ]
    rep = calibrate(rows)
    assert set(rep) == {"80-84|T2", "90-94|T1"}, "OPEN dikecualikan, tier dipisah"
    assert rep["80-84|T2"]["winrate"] == 0.5 and rep["80-84|T2"]["n"] == 2
    assert bucket(100) == "100-104"
