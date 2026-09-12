"""Replay engine: putar candle demi candle dari timestamp entry.
Aturan konservatif intra-candle: bila satu candle menyentuh TP DAN SL,
dimenangkan SL (asumsi eksekusi terburuk). MFE/MAE dihitung dari high/low.
Bukan kristal: candle hourly bisa menyembunyikan whipsaw intra-jam —
hasil replay = estimasi optimistis-menengah, nyatakan begitu di report.
"""
from __future__ import annotations


def replay(entry_ts: int, entry: float, sl_pct: float, tp_pct: float,
           candles: list[dict], timeout_h: float | None = None) -> dict:
    sl = entry * (1 - abs(sl_pct) / 100)
    tp = entry * (1 + abs(tp_pct) / 100)
    mfe = 0.0
    mae = 0.0
    bars = 0
    future = [c for c in candles if int(c.get("ts", 0)) >= int(entry_ts)]
    if not future:
        return {"status": "NO_DATA", "pnl_pct": 0.0, "mfe": 0.0, "mae": 0.0, "bars": 0}
    for c in future:
        bars += 1
        try:
            hi, lo, cl = float(c["h"]), float(c["l"]), float(c["c"])
        except (KeyError, TypeError, ValueError):
            continue
        mfe = max(mfe, (hi - entry) / entry * 100)
        mae = min(mae, (lo - entry) / entry * 100)
        sl_hit = lo <= sl
        tp_hit = hi >= tp
        if sl_hit and tp_hit:
            return {"status": "SL", "pnl_pct": round(-abs(sl_pct), 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars,
                    "note": "TP+SL satu candle -> SL (konservatif)"}
        if sl_hit:
            return {"status": "SL", "pnl_pct": round(-abs(sl_pct), 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars}
        if tp_hit:
            return {"status": "TP", "pnl_pct": round(abs(tp_pct), 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars}
        if timeout_h is not None and (int(c["ts"]) - int(entry_ts)) >= timeout_h * 3600:
            pnl = (cl - entry) / entry * 100
            return {"status": "TIMEOUT", "pnl_pct": round(pnl, 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars}
    last = float(future[-1].get("c", entry))
    return {"status": "OPEN", "pnl_pct": round((last - entry) / entry * 100, 2),
            "mfe": round(mfe, 2), "mae": round(mae, 2), "bars": bars}

def bucket(conf: float, width: int = 5) -> str:
    lo = int(float(conf) // width * width)
    return f"{lo}-{lo + width - 1}"

def calibrate(rows: list[dict], width: int = 5) -> dict:
    """rows: [{conf, tier, pnl_pct, status}] dengan status TP/SL/TIMEOUT/TRAIL.
    Return per-bucket + per-tier: {n, winrate, avg_win, avg_loss, expectancy, avg_mfe, avg_mae}.
    """
    from .engine import CLOSED_STATUSES, expectancy
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("status") not in CLOSED_STATUSES:
            continue
        key = f"{bucket(r.get('conf', 0), width)}|T{r.get('tier', 1)}"
        b = out.setdefault(key, {"n": 0, "wins": 0, "pnl": [], "mfe": [], "mae": []})
        b["n"] += 1
        if float(r.get("pnl_pct", 0)) > 0:
            b["wins"] += 1
        b["pnl"].append(float(r.get("pnl_pct", 0)))
        if r.get("mfe") is not None:
            b["mfe"].append(float(r["mfe"]))
        if r.get("mae") is not None:
            b["mae"].append(float(r["mae"]))
    rep = {}
    for k, b in sorted(out.items()):
        wins = [x for x in b["pnl"] if x > 0]
        losses = [x for x in b["pnl"] if x <= 0]
        wr = b["wins"] / b["n"]
        aw = sum(wins) / len(wins) if wins else 0.0
        al = abs(sum(losses) / len(losses)) if losses else 0.0
        rep[k] = {"n": b["n"], "winrate": round(wr, 3),
                  "avg_win": round(aw, 2), "avg_loss": round(al, 2),
                  "expectancy": round(expectancy(wr, aw, al), 2),
                  "avg_mfe": round(sum(b["mfe"]) / len(b["mfe"]), 2) if b["mfe"] else 0.0,
                  "avg_mae": round(sum(b["mae"]) / len(b["mae"]), 2) if b["mae"] else 0.0}
    return rep
