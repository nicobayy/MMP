"""Backtest + expectancy report.
V1 jujur: tanpa histori candle, backtest = ukur return sinyal PASS
dari harga entry (DB) ke harga sekarang (DexScreener live),
dengan simulasi TP/SL/time-stop. Bukan klaim win-rate masa lalu.
"""
from __future__ import annotations


def expectancy(winrate: float, avg_win: float, avg_loss: float) -> float:
    """E = p*W - (1-p)*L. Harus > 0 agar layak."""
    return winrate * avg_win - (1 - winrate) * avg_loss

def apply_costs(pnl_pct: float, slippage_pct: float = 0.5, fee_pct: float = 0.2) -> float:
    """PnL bersih setelah asumsi biaya round-trip (masuk+keluar).
    Model kasar & eksplisit: bukan simulasi order book. Naikkan angka ini
    bila main token tipis (slippage nyata memecoin sering >2%).
    """
    return round(pnl_pct - 2 * (abs(slippage_pct) + abs(fee_pct)), 2)


def effective_costs(liq_usd: float | None, base_slip: float = 0.5,
                    base_fee: float = 0.2, cfg: dict | None = None) -> tuple[float, float]:
    """M4: biaya berjenjang likuiditas — token tipis bayar slippage lebih mahal.

    Tier default (override via paper.cost_tiers = [[batas_liq, slip_pct], ...]
    terurut naik; fee tetap base_fee):
      liq < 50k  -> slip 2.0% (memecoin tipis, whipsaw + MEV)
      liq < 100k -> slip 1.0%
      lain       -> base_slip (config paper.slippage_pct)
    Return (slip, fee). Jujur: tetap asumsi, bukan hasil ukur order book.
    """
    tiers = None
    try:
        tiers = (cfg.get("paper") or {}).get("cost_tiers") if cfg else None
    except Exception:
        tiers = None
    if not tiers:
        tiers = [[50000, 2.0], [100000, 1.0]]
    try:
        liq = float(liq_usd or 0)
    except (TypeError, ValueError):
        liq = 0.0
    for bound, slip in sorted(tiers, key=lambda t: float(t[0])):
        try:
            if liq < float(bound):
                return float(slip), float(base_fee)
        except (TypeError, ValueError):
            continue
    return float(base_slip), float(base_fee)

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
