"""Regression tests untuk temuan HIGH (H1-H5): veto umur, dual jujur, settle replay, atribusi, win konsisten."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.analyzers import risk as risk_an
from mmp.engine.signal import _dual_check
from mmp.storage import kol as koldb


def _pair_no_age():
    return {"chainId": "base", "liquidity": {"usd": 100000}, "volume": {"h24": 200000},
            "txns": {"h24": {"buys": 200, "sells": 200}}, "marketCap": 1000000, "fdv": 1000000}


def test_h1_unknown_age_veto_opt_in():
    cfg_off = {"risk": {"min_liquidity_usd": 1, "min_volume_h24_usd": 1, "min_txns_h24": 1,
                        "max_fdv_to_mcap_ratio": 99.0, "min_pair_age_minutes": 60,
                        "blocked_labels": []}}
    assert risk_an.check_hard_veto(_pair_no_age(), cfg_off) == []
    cfg_on = {"risk": {**cfg_off["risk"], "veto_on_unknown_age": True}}
    vetoes = risk_an.check_hard_veto(_pair_no_age(), cfg_on)
    assert any("AGE_UNKNOWN" in v for v in vetoes)


def test_h2_dual_evm_label_honest():
    cfg = {"tiers": {"dual_max_divergence": 3.0, "tier2_evm_tax_required": True}}
    pair = {"chainId": "base"}
    ok, note = _dual_check(pair, {"source_honeypot_is": True, "buy_tax": 2.0, "sell_tax": 3.0}, cfg)
    assert ok is True and "tax-verified" in note and "setuju" not in note


def test_h5_kol_win_is_net_pnl_not_reason():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE kol_callouts(id INTEGER PRIMARY KEY AUTOINCREMENT, ts DATETIME DEFAULT CURRENT_TIMESTAMP, source TEXT DEFAULT '', handle TEXT DEFAULT '', token TEXT DEFAULT '', symbol TEXT DEFAULT '', chain TEXT DEFAULT '', trusted INTEGER DEFAULT 0, note TEXT DEFAULT '')")
    con.execute("CREATE TABLE paper_positions(id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT DEFAULT '', status TEXT DEFAULT '', pnl_pct REAL DEFAULT 0, close_reason TEXT DEFAULT '')")
    koldb.init(con)
    koldb.add_callout(con, "TOK", "T", handle="@h")
    # TIMEOUT hijau (+5%) = win; TIMEOUT merah (-2%) = loss
    con.execute("INSERT INTO paper_positions(token,status,pnl_pct,close_reason) VALUES('TOK','CLOSED',5.0,'TIMEOUT'),('TOK','CLOSED',-2.0,'TIMEOUT')")
    st = koldb.handle_stats(con, "@h")
    assert (st["wins"], st["losses"], st["win_rate"]) == (1, 1, 0.5)
