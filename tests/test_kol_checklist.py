import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.analyzers import kol as kol_an
from mmp.analyzers import risk as risk_an
from mmp.notifiers.telegram import format_checklist
from mmp.storage import kol as koldb


def _mem():
    con = sqlite3.connect(":memory:")
    koldb.init(con)
    con.execute(
        "CREATE TABLE paper_positions(id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT DEFAULT '',"
        " status TEXT DEFAULT 'OPEN', pnl_pct REAL DEFAULT NULL, close_reason TEXT DEFAULT '')"
    )
    return con


def test_handle_weight_graduated_and_capped():
    con = _mem()
    w, label = koldb.handle_weight(con, "@new")
    assert (w, "belum ada outcome" in label) == (0.5, True)
    koldb.add_callout(con, "T1", handle="@p", trust="trusted")
    for _ in range(3):
        con.execute("INSERT INTO paper_positions(token,status,pnl_pct,close_reason)"
                    " VALUES('T1','CLOSED',30.0,'TP')")
    w2, _ = koldb.handle_weight(con, "@p", "trusted")
    assert w2 == 1.5
    w3, _ = koldb.handle_weight(con, "@p", "trial")
    assert w3 == 1.0, "plafon trial memotong proven"
    koldb.add_callout(con, "T2", handle="@bad", trust="trusted")
    for _ in range(4):
        con.execute("INSERT INTO paper_positions(token,status,pnl_pct,close_reason)"
                    " VALUES('T2','CLOSED',-15.0,'SL')")
    w4, label4 = koldb.handle_weight(con, "@bad", "trusted")
    assert w4 == 0.0 and "downranked" in label4


def test_kol_dedupe_and_trust_tiers():
    s, _, meta = kol_an.analyze_kol(
        {}, [{"handle": "@a", "weight": 1.5}, {"handle": "@A", "weight": 1.0}])
    assert meta["handles"] == 1 and meta["trusted_eff"] == 1.5, "case-insensitive dedupe"
    s2, _, _ = kol_an.analyze_kol(
        {}, [{"handle": f"@h{i}", "weight": 1.5} for i in range(10)])
    assert s2 == 100.0, "eff di-cap 3.0 -> skor max 100"


def test_add_callout_trust_reason_stored():
    con = _mem()
    rid = koldb.add_callout(con, "MINT", "S", handle="@x", trust="trial", reason="whale_buy")
    assert rid > 0
    rows = koldb.recent_for_token(con, "MINT", 48)
    assert rows[0]["trust"] == "trial" and rows[0]["reason"] == "whale_buy"


def test_security_checklist_statuses():
    en = {"mint_renounced": True, "buy_tax": 2.0, "sell_tax": 3.0,
          "source_honeypot_is": True, "top10_pct": 20.0}
    cl = risk_an.security_checklist({"chainId": "base"}, en, {"ok": True, "note": "setuju"}, "COMPLETE")
    by = {c["item"]: c["status"] for c in cl}
    assert by == {"mint": "OK", "freeze": "OK", "tax": "OK", "honeypot": "OK",
                  "top10": "OK", "lp_lock": "UNKNOWN", "dual": "OK", "grade": "OK"}
    bad = dict(en, labels=["honeypot", "mintable-risk", "freezable-risk"],
               buy_tax=99.0, sell_tax=99.0, top10_pct=80.0)
    cl2 = risk_an.security_checklist({"chainId": "bsc"}, bad, {"ok": False, "note": "x"}, "BLIND")
    by2 = {c["item"]: c["status"] for c in cl2}
    assert by2["mint"] == "FAIL" and by2["freeze"] == "FAIL" and by2["honeypot"] == "FAIL"
    assert by2["tax"] == "FAIL" and by2["top10"] == "FAIL" and by2["grade"] == "WARN"
    empty = risk_an.security_checklist({"chainId": "solana"}, {}, {}, "?")
    assert {c["item"]: c["status"] for c in empty}["lp_lock"] == "UNKNOWN"
    txt = format_checklist({"meta": {"checklist": cl}})
    assert txt.startswith("Audit:") and "mint" in txt
    assert format_checklist({}) == ""
