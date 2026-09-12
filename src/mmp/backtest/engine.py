"""Backtest + expectancy report.
V1 jujur: tanpa histori candle, backtest = ukur return sinyal PASS
dari harga entry (DB) ke harga sekarang (DexScreener live),
dengan simulasi TP/SL/time-stop. Bukan klaim win-rate masa lalu.
"""
from __future__ import annotations


def expectancy(winrate: float, avg_win: float, avg_loss: float) -> float:
    """E = p*W - (1-p)*L. Harus > 0 agar layak."""
    return winrate * avg_win - (1 - winrate) * avg_loss


# Status yang dianggap posisi sudah tutup (masuk expectancy/report/kalibrasi).
CLOSED_STATUSES = ("TP", "SL", "TIMEOUT", "TRAIL")

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
    closed = [o for o in outcomes if o.get("status") in CLOSED_STATUSES]
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
            "sl": sum(1 for o in closed if o["status"] == "SL"),
            "trail": sum(1 for o in closed if o["status"] == "TRAIL")}


def simulate_trailing_exit(entry_ts: int, entry: float, candles: list[dict],
                           sl_pct: float, tp_pct: float | None = None,
                           timeout_h: float | None = None,
                           activation_pct: float = 8.0,
                           callback_pct: float = 4.0) -> dict:
    """Simulasi exit cepat + trailing stop di atas candle.

    Aturan (konservatif, konsisten dengan replay()):
    - SL tetap selalu aktif; bila satu candle menyentuh SL dan target lain,
      dimenangkan SL (asumsi eksekusi terburuk).
    - TP tetap (bila tp_pct diberikan) = exit cepat saat high menyentuh target.
    - Setelah peak >= activation, stop naik mengikuti peak*(1-callback);
      low menyentuh stop -> TRAIL (kunci profit runner).
    - Timeout dihitung dari timestamp candle seperti replay().
    Return dict {status, pnl_pct, exit_price, mfe, mae, bars, note}.
    """
    if not entry or entry <= 0:
        return {"status": "UNKNOWN", "pnl_pct": 0.0, "exit_price": 0.0,
                "mfe": 0.0, "mae": 0.0, "bars": 0}
    sl = float(entry) * (1 - abs(float(sl_pct)) / 100)
    tp = float(entry) * (1 + abs(float(tp_pct)) / 100) if tp_pct else None
    cb = abs(float(callback_pct)) / 100
    act = abs(float(activation_pct)) / 100
    mfe = 0.0
    mae = 0.0
    bars = 0
    peak = float(entry)
    trail: float | None = None
    future = [c for c in (candles or []) if int(c.get("ts", 0)) >= int(entry_ts)]
    if not future:
        return {"status": "NO_DATA", "pnl_pct": 0.0, "exit_price": 0.0,
                "mfe": 0.0, "mae": 0.0, "bars": 0}
    for c in future:
        bars += 1
        try:
            hi, lo, cl = float(c["h"]), float(c["l"]), float(c["c"])
        except (KeyError, TypeError, ValueError):
            continue
        mfe = max(mfe, (hi - entry) / entry * 100)
        mae = min(mae, (lo - entry) / entry * 100)
        peak = max(peak, hi)
        if trail is None and (peak - entry) / entry >= act:
            trail = peak * (1 - cb)
        elif trail is not None:
            trail = max(trail, peak * (1 - cb))
        sl_hit = lo <= sl
        tp_hit = tp is not None and hi >= tp
        trail_hit = trail is not None and lo <= trail
        if sl_hit:
            return {"status": "SL", "pnl_pct": round(-abs(float(sl_pct)), 2),
                    "exit_price": round(sl, 8),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars,
                    "note": "SL didahulukan (konservatif)"}
        if tp_hit:
            assert tp is not None
            return {"status": "TP", "pnl_pct": round(abs(float(tp_pct or 0)), 2),
                    "exit_price": round(tp, 8),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars,
                    "note": "TP cepat sebelum trailing"}
        if trail_hit:
            assert trail is not None
            return {"status": "TRAIL", "pnl_pct": round((trail - entry) / entry * 100, 2),
                    "exit_price": round(trail, 8),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars,
                    "note": f"trailing stop callback {callback_pct}% dari peak"}
        if timeout_h is not None and (int(c["ts"]) - int(entry_ts)) >= timeout_h * 3600:
            pnl = (cl - entry) / entry * 100
            return {"status": "TIMEOUT", "pnl_pct": round(pnl, 2),
                    "exit_price": round(cl, 8),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars}
    last = float(future[-1].get("c", entry))
    return {"status": "OPEN", "pnl_pct": round((last - entry) / entry * 100, 2),
            "exit_price": round(last, 8),
            "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars}
