"""Backtest + expectancy report.
V1 jujur: tanpa histori candle, backtest = ukur return sinyal PASS
dari harga entry (DB) ke harga sekarang (DexScreener live),
dengan simulasi TP/SL/time-stop. Bukan klaim win-rate masa lalu.
"""
from __future__ import annotations

def expectancy(winrate: float, avg_win: float, avg_loss: float) -> float:
    """E = p*W - (1-p)*L. Harus > 0 agar layak."""
    return winrate * avg_win - (1 - winrate) * avg_loss

def settle(entry: float, now: float, sl_pct: float, tp_pct: float, timeout_hit: bool = False) -> dict:
    """Tentukan outcome satu posisi: TP hit / SL hit / open/timeout."""
    if not entry or not now:
        return {"status": "UNKNOWN", "pnl_pct": 0.0}
    ret = (now - entry) / entry * 100
    if ret <= -abs(sl_pct):
        return {"status": "SL", "pnl_pct": round(-abs(sl_pct), 2)}
    if ret >= abs(tp_pct):
        return {"status": "TP", "pnl_pct": round(abs(tp_pct), 2)}
    if timeout_hit:
        return {"status": "TIMEOUT", "pnl_pct": round(ret, 2)}
    return {"status": "OPEN", "pnl_pct": round(ret, 2)}

def summarize(outcomes: list[dict]) -> dict:
    closed = [o for o in outcomes if o.get("status") in ("TP", "SL", "TIMEOUT")]
    if not closed:
        return {"n": 0, "winrate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0, "note": "belum ada posisi closed"}
    wins = [o for o in closed if o["pnl_pct"] > 0]
    losses = [o for o in closed if o["pnl_pct"] <= 0]
    wr = len(wins) / len(closed)
    aw = sum(o["pnl_pct"] for o in wins) / len(wins) if wins else 0.0
    al = abs(sum(o["pnl_pct"] for o in losses) / len(losses)) if losses else 0.0
    return {"n": len(closed), "winrate": round(wr, 3),
            "avg_win": round(aw, 2), "avg_loss": round(al, 2),
            "expectancy": round(expectancy(wr, aw, al), 2),
            "tp": sum(1 for o in closed if o["status"] == "TP"),
            "sl": sum(1 for o in closed if o["status"] == "SL")}
