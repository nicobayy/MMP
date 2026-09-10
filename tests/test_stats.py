import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.storage import stats as stats_mod


def test_summarize_batch_counts():
    items = [
        {"grade": "COMPLETE", "hp": "na"},
        {"grade": "PARTIAL", "hp": "ok"},
        {"grade": "PARTIAL", "hp": "no_tax"},
        {"grade": "BLIND", "hp": "fail"},
        {"grade": "?", "hp": "na"},
    ]
    st = stats_mod.summarize_batch(items)
    assert st == {"n": 5, "complete": 1, "partial": 2, "blind": 1,
                  "hp_ok": 1, "hp_no_tax": 1, "hp_fail": 1}


def test_coverage_report_thresholds():
    con = sqlite3.connect(":memory:")
    rep = stats_mod.coverage_report(con)
    assert rep["batches"] == 0 and rep["hp_gap_pct"] == 0.0
    stats_mod.save_batch(con, {"n": 10, "complete": 8, "partial": 2, "blind": 0,
                               "hp_ok": 9, "hp_no_tax": 1, "hp_fail": 0})
    stats_mod.save_batch(con, {"n": 10, "complete": 0, "partial": 0, "blind": 10,
                               "hp_ok": 0, "hp_no_tax": 6, "hp_fail": 4})
    rep2 = stats_mod.coverage_report(con)
    assert rep2["batches"] == 2 and rep2["signals"] == 20
    assert rep2["blind_pct"] == 50.0
    assert rep2["hp_tax_ok_pct"] == 45.0 and rep2["hp_gap_pct"] == 55.0
