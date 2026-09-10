import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.collectors import meter as _meter
from mmp.storage import wallets as wal


def _mem():
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE paper_positions(id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT DEFAULT '', status TEXT DEFAULT 'OPEN')"
    )
    con.execute(
        "CREATE TABLE wallets(wallet TEXT PRIMARY KEY, chain TEXT DEFAULT 'solana', label TEXT DEFAULT '', wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, total_pnl REAL DEFAULT 0.0, first_seen DATETIME DEFAULT CURRENT_TIMESTAMP, last_seen DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "CREATE TABLE wallet_sightings(id INTEGER PRIMARY KEY AUTOINCREMENT, wallet TEXT, token TEXT, symbol TEXT DEFAULT '', ts DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(wallet, token))"
    )
    con.execute(
        "CREATE TABLE whale_buys(id INTEGER PRIMARY KEY AUTOINCREMENT, wallet TEXT, token TEXT, side TEXT DEFAULT 'BUY', amount REAL DEFAULT 0, signature TEXT DEFAULT '', ts DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(wallet, token, signature))"
    )
    return con


def test_attribute_token_outcome_feeds_wallets():
    con = _mem()
    wal.add_sighting(con, "W1", "TOK")
    wal.add_sighting(con, "W2", "TOK")
    wal.add_sighting(con, "W3", "OTHER")
    # Tanpa bukti trade (whale_buys) -> tak ada atribusi (fail-closed, anti-karang track-record)
    assert wal.attribute_token_outcome(con, "TOK", True, 5.0) == 0
    assert wal.stats(con, "W1")["wins"] == 0
    wal.record_whale_flow(con, "W1", "TOK", "BUY", 10.0, "sig1", 1.0)
    wal.record_whale_flow(con, "W2", "TOK", "BUY", 10.0, "sig2", 1.0)
    wal.record_whale_flow(con, "W3", "OTHER", "BUY", 10.0, "sig3", 1.0)
    n = wal.attribute_token_outcome(con, "TOK", True, 5.0)
    assert n == 2
    assert wal.stats(con, "W1")["wins"] == 1
    assert wal.stats(con, "W2")["total_pnl"] == 5.0
    assert wal.stats(con, "W3")["wins"] == 0, "token lain tak boleh kena"
    n2 = wal.attribute_token_outcome(con, "TOK", False, -3.0)
    assert n2 == 2 and wal.stats(con, "W1")["losses"] == 1


def test_circuit_breaker_trips_and_resets():
    _meter.reset()
    _meter.set_budgets({"helius": 2})
    assert _meter.allow("helius") is True
    _meter.count("helius", 2)
    assert _meter.allow("helius") is False
    assert "TRIPPED" in _meter.line() and "helius=2/2" in _meter.line()
    assert _meter.allow("birdeye") is True, "tanpa budget = unlimited"
    _meter.reset()
    _meter.set_budgets({})
    assert _meter.allow("helius") is True
    _meter.reset()
