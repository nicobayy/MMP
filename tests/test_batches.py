import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import sqlite3

from mmp import safety as guard
from mmp.analyzers import kol as kol_an
from mmp.backtest.engine import apply_costs
from mmp.collectors import cache as _cache
from mmp.collectors import honeypot_is as hp
from mmp.collectors import meter as _meter
from mmp.storage import kol as koldb
from mmp.storage import wallets as wal


def _mem():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE paper_positions(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT DEFAULT '', chain TEXT DEFAULT '', token TEXT DEFAULT '', pair_addr TEXT DEFAULT '', entry REAL DEFAULT 0, sl REAL DEFAULT 0, tp REAL DEFAULT 0, risk_pct REAL DEFAULT 1.0, status TEXT DEFAULT 'OPEN', opened_ts DATETIME DEFAULT CURRENT_TIMESTAMP, closed_ts DATETIME DEFAULT NULL, exit_price REAL DEFAULT NULL, pnl_pct REAL DEFAULT NULL, close_reason TEXT DEFAULT '')")
    con.execute("CREATE TABLE kol_callouts(id INTEGER PRIMARY KEY AUTOINCREMENT, ts DATETIME DEFAULT CURRENT_TIMESTAMP, source TEXT DEFAULT '', handle TEXT DEFAULT '', token TEXT DEFAULT '', symbol TEXT DEFAULT '', chain TEXT DEFAULT '', trusted INTEGER DEFAULT 0, note TEXT DEFAULT '')")
    return con

CFG = {"portfolio": {"max_open_positions": 2, "max_per_chain": 1, "daily_stop_pct": -3.0}}

def test_kill_switch(tmp_path, monkeypatch):
    f = tmp_path / "STOP"
    monkeypatch.setenv("MMP_STOP", str(f))
    assert guard.is_killed() is False
    f.write_text("STOP")
    assert guard.is_killed() is True
    con = _mem()
    ok, why = guard.allow_new(con, CFG, "solana")
    assert ok is False and "KILL" in why

def test_guard_caps_and_daily_stop(monkeypatch):
    monkeypatch.delenv("MMP_STOP", raising=False)
    con = _mem()
    ok, _ = guard.allow_new(con, CFG, "solana")
    assert ok is True
    con.execute("INSERT INTO paper_positions(symbol,chain,pair_addr,status) VALUES('A','solana','P1','OPEN'),('B','solana','P2','OPEN')")
    ok, why = guard.allow_new(con, CFG, "base")
    assert ok is False and "max open" in why
    ok, why = guard.allow_new(con, CFG, "solana", for_alert=True)
    assert ok is True, "caps tak boleh blokir alert"
    con.execute("INSERT INTO paper_positions(symbol,chain,status,pnl_pct,risk_pct,entry,sl,closed_ts) VALUES('C','solana','CLOSED',-5.0,1.0,100,85,CURRENT_TIMESTAMP)")
    ok, why = guard.allow_new(con, CFG, "base", for_alert=True)
    assert ok is True, "satu rugi kecil (-0.33pct modal) tak boleh memicu daily-stop -3.0"
    assert round(guard.realized_today(con), 2) == -0.33
    con.execute("INSERT INTO paper_positions(symbol,chain,status,pnl_pct,risk_pct,entry,sl,closed_ts) VALUES('D','solana','CLOSED',-16.4,1.0,100,85,CURRENT_TIMESTAMP),('E','solana','CLOSED',-16.4,1.0,100,85,CURRENT_TIMESTAMP),('F','solana','CLOSED',-16.4,1.0,100,85,CURRENT_TIMESTAMP)")
    ok, why = guard.allow_new(con, CFG, "base", for_alert=True)
    assert ok is False and "daily-stop" in why

def test_apply_costs():
    assert apply_costs(30.0, 0.5, 0.2) == 28.6
    assert apply_costs(-15.0, 0.5, 0.2) == -16.4

def test_honeypot_mapping(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"honeypotResult": {"isHoneypot": False},
                                "simulationResult": {"buyTax": 2.5, "sellTax": 3.0},
                                "summary": {"risk": "low", "flags": []}}
    monkeypatch.setattr(hp.requests, "get", lambda *a, **k: Resp())
    en = hp.build_enrichment("base", "0xabc")
    assert en["buy_tax"] == 2.5 and en["sell_tax"] == 3.0 and "labels" not in en
    assert en["hp_risk"] == "low"
    class Resp2(Resp):
        def json(self): return {"honeypotResult": {"isHoneypot": True},
                                "simulationResult": {"buyTax": 99, "sellTax": 99},
                                "summary": {"risk": "high", "flags": ["high-tax"]}}
    monkeypatch.setattr(hp.requests, "get", lambda *a, **k: Resp2())
    en2 = hp.build_enrichment("bsc", "0xdef")
    assert "honeypot" in en2["labels"] and en2["hp_flags"] == ["high-tax"]
    class RespLegacy(Resp):
        def json(self): return {"isHoneypot": False, "buyTax": 1.0, "sellTax": 1.0}
    monkeypatch.setattr(hp.requests, "get", lambda *a, **k: RespLegacy())
    en3 = hp.build_enrichment("base", "0xabc")
    assert en3["buy_tax"] == 1.0, "fallback bentuk v1 datar tetap didukung"
    assert hp.build_enrichment("solana", "MINT") == {}
    monkeypatch.setattr(hp.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert hp.build_enrichment("base", "0xabc") == {}

def test_wallet_confidence():
    assert wal.confidence(0, 0) == 0.5
    assert wal.confidence(5, 0) == 0.75, "5W/0L disusutkan, bukan 1.0"
    assert wal.confidence(8, 2) == 0.8
    b, n = wal.overlap_bonus(["a", "b"], ["a", "b"], weights={"a": 0.5, "b": 1.0})
    assert (b, n) == (7.5, 2)
    b2, n2 = wal.overlap_bonus(["a", "b"], ["a", "b"])
    assert (b2, n2) == (10.0, 2), "legacy tanpa weights tetap"

def test_kol_winrate_and_shilling():
    con = _mem()
    koldb.init(con)  # migrasi kolom trust/reason (produksi selalu init dulu)
    koldb.add_callout(con, "T1", "F", handle="@a", trusted=True)
    koldb.add_callout(con, "T1", "F", handle="@b", trusted=True)
    koldb.add_callout(con, "T1", "F", handle="@c", trusted=False)
    assert koldb.recent_handles_count(con, "T1", 6) == 3
    st = koldb.handle_stats(con, "@a")
    assert st == {"calls": 1, "wins": 0, "losses": 0, "win_rate": 0.0, "proven": False}
    con.execute("INSERT INTO paper_positions(symbol,token,status,pnl_pct,close_reason) VALUES('F','T1','CLOSED',30.0,'TP'),('F','T1','CLOSED',30.0,'TP'),('F','T1','CLOSED',30.0,'TP')")
    st2 = koldb.handle_stats(con, "@a")
    assert st2["proven"] is True and st2["win_rate"] == 1.0
    s, notes, meta = kol_an.analyze_kol({}, [{"handle": "@a", "weight": 1.5}, {"handle": "@b", "weight": 1.0}])
    assert s == 40 + 2.5 * 20 and meta["trusted_eff"] == 2.5
    spam, _, _ = kol_an.analyze_kol({}, [{"handle": "@a", "weight": 1.5}] * 5)
    assert spam == 40 + 1.5 * 20, "spam 1 handle = 1 suara (dedupe)"
    noise, _, _ = kol_an.analyze_kol({}, [{"handle": "@x"}])
    assert noise == 40.0, "tanpa weight/trusted = nol (fail-closed)"

def test_cache_and_meter():
    _cache.clear()
    _meter.reset()
    assert _cache.get("k", 60) is None
    _cache.put("k", [1], ttl=60)
    assert _cache.get("k", 60) == [1]
    _meter.count("dexscreener")
    _meter.count("dexscreener")
    assert _meter.summary() == {"dexscreener": 2}
    assert "dexscreener=2" in _meter.line()
    _meter.reset()
    _cache.clear()
