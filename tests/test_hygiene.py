import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp import validators as v
from mmp.analyzers import liquidity as liq_an
from mmp.storage import kol as koldb


def test_validators():
    assert v.is_solana_address("So11111111111111111111111111111111111111112")
    assert v.is_token_address("solana", "So11111111111111111111111111111111111111112")
    assert not v.is_solana_address("0x123")
    assert not v.is_solana_address("So111!!bad chars ##")
    assert not v.is_solana_address("")
    assert v.is_evm_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    assert v.is_token_address("base", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    assert not v.is_evm_address("0xZZZ")
    assert not v.is_evm_address("12345")
    assert "base58" in v.explain("solana", "x") and "0x" in v.explain("base", "x")


def test_impact_key_renamed_with_fallback():
    pair = {"chainId": "base", "dexId": "uniswap", "liquidity": {"usd": 10000},
            "volume": {"h24": 50000, "h1": 2000}, "txns": {"h24": {"buys": 100, "sells": 90}},
            "priceChange": {"h1": 0, "h24": 10}}
    cfg_new = {"liquidity": {"min_liquidity_usd": 30000, "min_volume_to_liquidity_ratio": 1.0,
                             "max_price_impact_1k_pct": 5.0}}
    s_new, _, _ = liq_an.analyze_exit(pair, cfg_new)
    cfg_old = {"liquidity": {"min_liquidity_usd": 30000, "min_volume_to_liquidity_ratio": 1.0,
                             "max_price_impact_1sol_pct": 5.0}}
    s_old, _, _ = liq_an.analyze_exit(pair, cfg_old)
    assert s_new == s_old, "fallback key lama tetap dihormati"


def test_kol_trust_tiers_and_reasons():
    con = sqlite3.connect(":memory:")
    koldb.init(con)
    koldb.add_callout(con, "M1", handle="@t", trust="trial", reason="whale_buy")
    koldb.add_callout(con, "M1", handle="@u", trust="untrusted", reason="launch")
    rows = {r["handle"]: r for r in koldb.recent_for_token(con, "M1", 48)}
    # L6: handle dinormalisasi tanpa '@' di titik tulis.
    assert rows["t"]["trust"] == "trial" and rows["t"]["reason"] == "whale_buy"
    assert rows["u"]["trust"] == "untrusted"
    assert koldb.handle_weight(con, "@t", "trial")[0] == 0.5
    assert koldb.handle_weight(con, "@u", "untrusted")[0] == 0.5
    # legacy boolean tetap jalan
    koldb.add_callout(con, "M2", handle="@old", trusted=True)
    assert koldb.recent_for_token(con, "M2", 48)[0]["trust"] == "trusted"
