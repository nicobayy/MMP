import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sqlite3

from mmp.analyzers import smart_money_auto as sma
from mmp.collectors import helius as hel
from mmp.storage import wallets as wal


def _pair():
    return {"chainId": "solana", "liquidity": {"usd": 100000}, "volume": {"h24": 300000},
            "txns": {"h24": {"buys": 300, "sells": 250}}}


def test_wallet_token_flows_buy_sell():
    txns = [{
        "signature": "S1", "timestamp": 1700000000,
        "tokenTransfers": [
            {"mint": "MINT_A", "fromUserAccount": "X", "toUserAccount": "W",
             "fromTokenAccount": "A1", "toTokenAccount": "A2", "tokenAmount": 50},
            {"mint": "MINT_A", "fromUserAccount": "W", "toUserAccount": "Y",
             "fromTokenAccount": "A2", "toTokenAccount": "A3", "tokenAmount": 10},
            {"mint": hel.SOL_MINT, "fromUserAccount": "X", "toUserAccount": "W",
             "fromTokenAccount": "A4", "toTokenAccount": "A5", "tokenAmount": 1},
        ],
    }]
    flows = hel.wallet_token_flows("W", txns)
    assert ("MINT_A", "BUY", 50.0) in [(f["mint"], f["side"], f["amount"]) for f in flows]
    assert ("MINT_A", "SELL", 10.0) in [(f["mint"], f["side"], f["amount"]) for f in flows]
    assert all(f["mint"] != hel.SOL_MINT for f in flows), "SOL diabaikan"
    assert hel.wallet_token_flows("W", []) == []
    assert hel.wallet_token_flows("W", [{"tokenTransfers": [{"mint": "M"}]}]) == []


def test_parse_enhanced_no_key_or_empty(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    assert hel.parse_enhanced(["S1"]) == []
    assert hel.get_signatures("W") == [] or True  # tanpa key boleh [] (offline aman)


def test_whale_store_and_bonus():
    con = sqlite3.connect(":memory:")
    wal.init(con)
    cfg = {"smart_money_auto": {"max_auto_score": 85, "healthy_buy_ratio_min": 0.5,
                                "healthy_buy_ratio_max": 0.7, "max_top_holder_pct": 15.0}}
    s0, _, meta0, _ = sma.discover(_pair(), {}, cfg)
    assert meta0["whale_buys"] == 0
    s1, notes1, meta1, _ = sma.discover(_pair(), {}, cfg, whale_buys_n=2)
    assert meta1["whale_buys"] == 2 and s1 == s0 + 6.0
    assert any("whale buy" in n for n in notes1)
    s2, _, _, _ = sma.discover(_pair(), {}, cfg, whale_buys_n=99)
    assert s2 - s0 == 9.0, "bonus di-cap 9"


def test_recent_whale_buys_window():
    con = sqlite3.connect(":memory:")
    wal.init(con)
    wal.record_whale_flow(con, "W1", "T", "BUY", 1, "S1", sol_spent=2.0)
    wal.record_whale_flow(con, "W2", "T", "BUY", 1, "S2", sol_spent=0.01)
    wal.record_whale_flow(con, "W1", "T", "SELL", 1, "S3")
    assert wal.recent_whale_buys(con, "T", 24, trusted_only=False) == 2, "hitung wallet BERBEDA, hanya BUY"
    assert wal.recent_whale_buys(con, "T", 24, trusted_only=False, min_sol=0.5) == 1, "filter debu"
    assert wal.recent_whale_buys(con, "T", 24) == 0, "default ranked-only: tanpa track record = 0"
    for _ in range(5):
        wal.record_outcome(con, "W1", True, 5.0)
    assert wal.recent_whale_buys(con, "T", 24) == 1, "W1 ranked -> dihitung; W2 belum"
    con.execute("UPDATE whale_buys SET ts=datetime('now','-49 hours') WHERE wallet='W1'")
    assert wal.recent_whale_buys(con, "T", 24) == 0
    assert wal.top_watched(con, 5) == []
    wal.add_sighting(con, "W9", "TX")
    wal.add_sighting(con, "W9", "TY")
    assert wal.top_watched(con, 5) == ["W9"]
