import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.backtest.engine import effective_costs
from mmp.collectors import helius as hel
from mmp.config import validate_config
from mmp.engine import gate as gt
from mmp.risk.position import build_plan, position_size_usd
from mmp.storage import kol as koldb
from mmp.storage.store import connect


def _base_cfg():
    return {
        "signal": {"min_confidence": 85, "permissive_confidence": 65},
        "tiers": {"tier2_min": 75},
        "weights": {"liquidity_exit": 25, "risk_safety": 25, "token_metrics": 20,
                    "smart_money": 20, "kol": 10},
        "risk": {}, "liquidity": {}, "token_metrics": {},
        "position": {"max_risk_per_trade_pct": 1.0, "default_stop_loss_pct": 15.0,
                     "default_take_profit_pct": 30.0, "min_reward_risk": 1.5,
                     "capital_usd": 1000},
        "chains": {}, "paper": {},
    }


def test_h1_cache_key_includes_chain():
    from mmp.collectors import cache
    from mmp.collectors import dexscreener as dex
    cache.clear()
    calls = []

    class R:
        def raise_for_status(self): pass
        def json(self): return {"pairs": [{"chainId": "base", "liquidity": {"usd": 1}}]}

    import mmp.collectors.dexscreener as mod
    orig = mod.requests.get
    mod.requests.get = lambda url, timeout=15: calls.append(url) or R()
    try:
        dex.get_token_pairs("base", "0xABC")
        dex.get_token_pairs("bsc", "0xABC")
    finally:
        mod.requests.get = orig
    assert len(calls) == 2, "chain berbeda wajib fetch ulang, bukan reuse cache"


def test_h2_permissive_threshold_from_config():
    cfg = _base_cfg()
    cfg["signal"]["permissive_confidence"] = 60
    v, reason, th, tier = gt.decide([], 62.0, cfg, permissive=True)
    assert (v, th, tier) == ("PASS", 60, 1), reason
    assert gt.permissive_threshold({}) == 65.0


def test_h3_config_validation():
    cfg = _base_cfg()
    validate_config(cfg)
    bad = _base_cfg()
    bad["weights"]["kol"] = 99
    try:
        validate_config(bad)
        raise AssertionError("weights != 100 harus ditolak")
    except ValueError:
        pass
    bad2 = _base_cfg()
    bad2["tiers"]["tier2_min"] = 90
    try:
        validate_config(bad2)
        raise AssertionError("tier2 >= t1 harus ditolak")
    except ValueError:
        pass


def test_m1_helius_redact():
    out = hel._redact("boom https://x/?api-key=SECRET123 oops")
    assert "SECRET123" not in out and "api-key=***" in out


def test_m4_effective_costs_tiers():
    s, f = effective_costs(20_000)
    assert s == 2.0 and f == 0.2
    s2, _ = effective_costs(80_000)
    assert s2 == 1.0
    s3, _ = effective_costs(500_000, base_slip=0.5)
    assert s3 == 0.5


def test_m5_pair_validator():
    from mmp import validators as v
    assert v.is_pair_address("solana", "J" * 40) is True
    assert v.explain_pair("bsc", "x").startswith("alamat pair EVM")


def test_l3_position_size():
    assert position_size_usd(1000, 1.0, 15.0) == 66.67
    assert position_size_usd(None, 1.0, 15.0) is None
    plan = build_plan(10.0, _base_cfg())
    assert plan["size_usd"] == 66.67 and plan["qty"] == 6.667
    plan2 = build_plan(10.0, _base_cfg(), capital_usd=None)
    assert plan2["size_usd"] is None


def test_l6_handle_normalization():
    assert koldb.normalize_handle("@Kanal") == "kanal"
    con = connect(":memory:")
    koldb.init(con)
    koldb.add_callout(con, "T1", handle="@Kanal")
    rows = koldb.recent_for_token(con, "T1", hours=48)
    assert rows and rows[0]["handle"] == "kanal"
