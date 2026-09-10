"""Position sizing + TP/SL + expectancy check.
L3: plan membawa size nyata (token + USD) dari modal & risiko config,
bukan cuma note. Rumus klasik: risk_usd = modal*risk_pct/100,
size_usd = risk_usd/(sl_pct/100). Tanpa modal (paper lama) -> size None
+ note, bukan angka karangan.
"""
from __future__ import annotations


def position_size_usd(capital_usd: float | None, risk_pct: float, sl_pct: float) -> float | None:
    try:
        cap = float(capital_usd) if capital_usd is not None else 0.0
        sl = abs(float(sl_pct))
    except (TypeError, ValueError):
        return None
    if cap <= 0 or sl <= 0:
        return None
    return round(cap * float(risk_pct) / 100 / (sl / 100), 2)


_UNSET: object = object()


def build_plan(entry: float, cfg: dict, capital_usd: float | None | object = _UNSET,
               risk_pct: float | None = None) -> dict:
    p = cfg["position"]
    sl_pct = float(p["default_stop_loss_pct"])
    tp_pct = float(p["default_take_profit_pct"])
    sl = entry * (1 - sl_pct / 100) if entry else 0
    tp = entry * (1 + tp_pct / 100) if entry else 0
    rr = (tp_pct / sl_pct) if sl_pct else 0
    # Jujur: RR config itu statis. expectancy_ok False bila entry tak valid
    # (harga 0) karena plan tak bisa dieksekusi; True = plan valid, BUKAN jaminan profit.
    ok = bool(entry) and rr >= float(p["min_reward_risk"])
    risk = float(risk_pct) if risk_pct is not None else float(p["max_risk_per_trade_pct"])
    # L3: _UNSET (arg tak diisi) -> baca position.capital_usd config.
    # None eksplisit -> size memang tak dihitung (paper lama), bukan fallback.
    if capital_usd is _UNSET:
        try:
            _c = p.get("capital_usd")
            capital_usd = float(_c) if _c is not None else None
        except (TypeError, ValueError, AttributeError):
            capital_usd = None
    cap_val = None if capital_usd is _UNSET else capital_usd
    cap_f: float | None = cap_val if isinstance(cap_val, (int, float)) else None
    size_usd = position_size_usd(cap_f, risk, sl_pct) if entry else None
    qty = round(size_usd / entry, 4) if size_usd and entry else None
    return {"entry": entry, "stop_loss": round(sl, 8), "take_profit": round(tp, 8),
            "sl_pct": sl_pct, "tp_pct": tp_pct, "RR": round(rr, 2),
            "max_risk_pct": p["max_risk_per_trade_pct"],
            "risk_pct": risk, "capital_usd": cap_val,
            "size_usd": size_usd, "qty": qty,
            "expectancy_ok": ok,
            "sizing_note": (f"Modal ${cap_val} risk {risk}%/SL {sl_pct}% -> size ${size_usd} ({qty} token)"
                            if size_usd else
                            f"Risiko maks {p['max_risk_per_trade_pct']}% modal per trade. Size = (modal*risk%)/SL%.")}
