import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mmp.backtest.engine import expectancy, settle, summarize
from mmp.collectors import birdeye as bir
from mmp.collectors import geckoterminal as gecko
from mmp.storage import kol as koldb
from mmp.storage import paper as pstore


def test_gecko_pool_normalize_offline():
    pool = {"attributes": {"address": "0xabc", "name": "FOO / USDC", "dex_id": "uniswap",
                           "base_token_price_usd": "1.5", "reserve_in_usd": "50000",
                           "volume_usd": {"h24": "80000", "h1": "2000"},
                           "transactions": {"h24": {"buys": 120, "sells": 100}},
                           "price_change_percentage": {"h1": "2", "h24": "10"},
                           "market_cap_usd": "1000000", "fdv_usd": "2000000"}}
    p = gecko.pool_to_pair(pool, "base")
    assert p["chainId"] == "base" and p["liquidity"]["usd"] == 50000
    assert p["txns"]["h24"] == {"buys": 120, "sells": 100}
    assert p["baseToken"]["symbol"] == "FOO"

def test_gecko_fallback_no_key_needed_but_offline_safe():
    out = gecko.universe_fallback({"geckoterminal": {"enabled": False}, "chains": {"enabled": ["base"]}})
    assert out == []

def test_birdeye_off_without_key(monkeypatch):
    monkeypatch.delenv("BIRDEYE_API_KEY", raising=False)
    assert bir.has_key() is False
    assert bir.build_enrichment("mint") == {}

def test_kol_storage_and_window():
    con = sqlite3.connect(":memory:")
    koldb.init(con)
    koldb.add_callout(con, "MINT1", "FOO", trusted=True, handle="@a")
    koldb.add_callout(con, "MINT1", "FOO", trusted=False, handle="@b")
    rows = koldb.recent_for_token(con, "MINT1", hours=48)
    assert len(rows) == 2 and sum(r["trusted"] for r in rows) == 1
    assert koldb.recent_for_token(con, "OTHER") == []

def test_backtest_settle_and_expectancy():
    assert settle(100, 130, 15, 30)["status"] == "TP"
    assert settle(100, 80, 15, 30)["status"] == "SL"
    assert settle(100, 110, 15, 30)["status"] == "OPEN"
    assert settle(0, 0, 15, 30)["status"] == "UNKNOWN"
    rep = summarize([{"status": "TP", "pnl_pct": 30}, {"status": "SL", "pnl_pct": -15}])
    assert rep["n"] == 2 and rep["winrate"] == 0.5 and rep["expectancy"] == expectancy(0.5, 30, 15)
    assert summarize([])["n"] == 0

def test_paper_open_settle_flow():
    con = sqlite3.connect(":memory:")
    pstore.init(con)
    sig = {"db_id": 1, "symbol": "FOO", "chain": "solana", "token_address": "M",
           "pair_address": "P", "price_usd": 100.0,
           "plan": {"stop_loss": 85.0, "take_profit": 130.0}}
    pid = pstore.open_from_signal(con, sig, 1.0)
    assert len(pstore.list_open(con)) == 1
    pstore.close_position(con, pid, 130.0, 30.0, "TP")
    assert pstore.list_open(con) == []
