"""Position sizing + TP/SL + expectancy check."""
from __future__ import annotations


def build_plan(entry: float, cfg: dict) -> dict:
    p = cfg["position"]
    sl_pct = float(p["default_stop_loss_pct"])
    tp_pct = float(p["default_take_profit_pct"])
    sl = entry * (1 - sl_pct / 100) if entry else 0
    tp = entry * (1 + tp_pct / 100) if entry else 0
    rr = (tp_pct / sl_pct) if sl_pct else 0
    # Jujur: RR config itu statis. expectancy_ok False bila entry tak valid
    # (harga 0) karena plan tak bisa dieksekusi; True = plan valid, BUKAN jaminan profit.
    ok = bool(entry) and rr >= float(p["min_reward_risk"])
    return {"entry": entry, "stop_loss": round(sl, 8), "take_profit": round(tp, 8),
            "sl_pct": sl_pct, "tp_pct": tp_pct, "RR": round(rr, 2),
            "max_risk_pct": p["max_risk_per_trade_pct"],
            "expectancy_ok": ok,
            "sizing_note": f"Risiko maks {p['max_risk_per_trade_pct']}% modal per trade. Size = (modal*risk%)/SL%."}
