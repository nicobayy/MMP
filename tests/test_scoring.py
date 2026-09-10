import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mmp.engine.scoring import weighted_score, apply_conservative_rules

def test_weighted():
    assert weighted_score({"a": 100, "b": 0}, {"a": 50, "b": 50}) == 50.0

def test_conservative_cap():
    cfg = {"weights": {"liquidity_exit": 25, "risk_safety": 25, "token_metrics": 20,
                       "smart_money": 20, "kol": 10},
           "signal": {"require_smart_money": True, "require_kol_or_sm": True}}
    scores = {"liquidity_exit": 100, "risk_safety": 100, "token_metrics": 100,
              "smart_money": 0, "kol": 0}
    conf, notes = apply_conservative_rules(scores, cfg)
    assert conf <= 69.0, "tanpa SM & KOL harus di-cap rendah (konservatif)"
