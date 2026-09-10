import sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mmp.storage import wallets as wal
from mmp.storage.store import should_alert, mark_alerted, SCHEMA
from mmp.notifiers.telegram import format_signal, format_summary

def test_wallet_winrate_and_trusted():
    con = sqlite3.connect(":memory:")
    wal.init(con)
    for _ in range(4):
        wal.record_outcome(con, "W1", True, 10.0)
    wal.record_outcome(con, "W1", False, -5.0)
    s = wal.stats(con, "W1")
    assert s["wins"] == 4 and s["losses"] == 1 and s["win_rate"] == 0.8
    assert wal.trusted(con, 5, 0.6) == ["W1"]
    assert wal.trusted(con, 6, 0.6) == []

def test_overlap_bonus():
    b, n = wal.overlap_bonus(["a", "b", "c"], ["b", "c", "z"])
    assert (b, n) == (10.0, 2)
    b2, n2 = wal.overlap_bonus([], ["b"])
    assert (b2, n2) == (0.0, 0)

def test_alert_cooldown():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    assert should_alert(con, "P1", 120) is True
    mark_alerted(con, "P1")
    assert should_alert(con, "P1", 120) is False
    assert should_alert(con, "P2", 120) is True

def test_telegram_format_escapes_html():
    sig = {"verdict": "PASS", "symbol": "<b>EVIL</b>", "chain": "solana", "confidence": 90,
           "threshold": 85, "price_usd": 0.01, "dex": "raydium", "reason": "ok <script>",
           "vetoes": [], "scores": {"smart_money": 70}, "plan": {}, "meta": {"sm": {"auto_score": 70, "trusted_overlap": 1}, "liquidity": {"liquidity_usd": 1}, "mcap": 1, "url": "https://x"}}
    t = format_signal(sig)
    assert "<script>" not in t and "&lt;script&gt;" in t
    s = format_summary(1, 2, [{"symbol": "A", "chain": "solana", "confidence": 90, "price_usd": 1}])
    assert "PASS=1" in s
