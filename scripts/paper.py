"""Paper trading CLI.
Usage:
  python scripts/paper.py --list
  python scripts/paper.py --settle            # tutup yg kena TP/SL/timeout
  python scripts/paper.py --settle --timeout-h 24
  python scripts/paper.py --settle --mark-to-market  # hanya tampilkan nilai kini, tak menutup posisi
  python scripts/paper.py --report            # expectancy dari posisi closed

Settle memakai replay candle (high/low) bila tersedia agar TP/SL yang
tersentuh intra-periode tak terlewat; fallback ke harga titik (mark-to-market)
bila candle kosong. Hasil replay = estimasi optimistis-menengah (candle hourly
menyembunyikan whipsaw intra-jam).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.backtest.engine import CLOSED_STATUSES, apply_costs, effective_costs, settle, simulate_trailing_exit, summarize
from mmp.backtest.replay import replay as replay_candles
from mmp.collectors import ohlcv as ohlcv_mod
from mmp.collectors import prices as pxr
from mmp.config import db_path, load_config
from mmp.storage import candles as cstore
from mmp.storage import paper as pstore
from mmp.storage import wallets as wal
from mmp.storage.store import connect


def live_price(chain: str, pair_addr: str, token: str = "") -> float:
    px, _src = pxr.resolve_price(chain, token, pair_addr)
    return px


def _epoch(ts: str) -> int:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # CURRENT_TIMESTAMP = UTC
        return int(dt.timestamp())
    except Exception:
        return 0

def settle_position(o: dict, cfg: dict, timeout_h: float, slip: float, fee: float,
                     con=None, end_ts: int | None = None) -> dict:
    """Tentukan outcome satu posisi paper. Return dict hasil settle.

    Prioritas: replay candle (high/low dari entry) -> fallback harga titik.
    end_ts opsional (epoch detik): batasi candle yang dipakai replay sampai
    momen close aktual — untuk perbandingan adil antar-profil di posisi yang
    sudah CLOSED (tanpa ini replay ikut membaca dump berhari-hari setelah
    close dan membalik TP asli jadi SL). Live settle tak mengisi ini.
    Return: {status, pnl_pct(net), exit_price, via} dengan via =
    'replay' | 'spot' | 'mark-to-market'. NO_DATA replay = fallback spot,
    bukan vonis.
    """
    sl_pct = float(cfg["position"]["default_stop_loss_pct"])
    tp_pct = float(cfg["position"]["default_take_profit_pct"])
    if o.get("entry") and o.get("sl"):
        try:
            sl_pct = abs((float(o["entry"]) - float(o["sl"])) / float(o["entry"]) * 100)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    if o.get("entry") and o.get("tp"):
        try:
            tp_pct = abs((float(o["tp"]) - float(o["entry"])) / float(o["entry"]) * 100)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    # 1. Replay candle (butuh pool + candle setelah entry)
    tf = str((cfg.get("backtest") or {}).get("replay_tf", "hour"))
    if tf not in ("minute", "hour", "day"):
        tf = "hour"
    tr = (cfg.get("paper") or {}).get("trailing") or {}
    tr_enabled = bool(tr.get("enabled", False))
    try:
        tr_act = float(tr.get("activation_pct", 8.0))
        tr_cb = float(tr.get("callback_pct", 4.0))
    except (TypeError, ValueError):
        tr_act, tr_cb = 8.0, 4.0
    pool = ohlcv_mod.resolve_pool(o.get("chain", "") or "", o.get("token", "") or "")
    candles: list = []
    if pool and con is not None:
        try:
            cstore.init(con)
            candles = cstore.get_candles(con, o.get("chain", ""), pool, tf,
                                         since=_epoch(o.get("opened_ts", "")) - 3600)
        except Exception:
            candles = []
        # Refresh bila kosong ATAU candle terbaru basi: tanpa ini replay jalan di
        # atas candle entry yang basi -> dump -22% tak terlihat -> OPEN selamanya
        # (kasus CATAI/Stunk: harga jebol SL 6% tapi posisi tak kunjung tutup).
        try:
            import time as _t
            newest = max(int(c.get("ts", 0)) for c in candles) if candles else 0
            stale = (not candles) or (_t.time() - newest > 1800)
        except Exception:
            stale = True
        if stale:
            try:
                fresh = ohlcv_mod.fetch(o.get("chain", ""), pool, tf,
                                        int((cfg.get("backtest") or {}).get("replay_limit", 500)))
                if fresh:
                    cstore.upsert_candles(con, o.get("chain", ""), pool, tf, fresh)
                    candles = cstore.get_candles(con, o.get("chain", ""), pool, tf,
                                                 since=_epoch(o.get("opened_ts", "")) - 3600)
            except Exception:
                pass
    if end_ts:
        try:
            candles = [c for c in candles if int(c.get("ts", 0)) <= int(end_ts)]
        except (TypeError, ValueError):
            pass
    if candles and tr_enabled:
        # Profil sniper: TP cepat + trailing runner (config paper.trailing).
        r = simulate_trailing_exit(_epoch(o.get("opened_ts", "")), float(o.get("entry") or 0),
                                   candles, sl_pct, tp_pct, timeout_h,
                                   activation_pct=tr_act, callback_pct=tr_cb)
        if r.get("status") in CLOSED_STATUSES:
            net = apply_costs(float(r.get("pnl_pct", 0.0)), slip, fee)
            return {"status": r["status"], "pnl_pct": net, "exit_price": r.get("exit_price", 0.0),
                    "via": "trail", "gross": float(r.get("pnl_pct", 0.0)), "pool": pool}
        # Tak menutup -> jatuh ke cek spot di bawah (jaring pengaman).
    elif candles:
        r = replay_candles(_epoch(o.get("opened_ts", "")), float(o.get("entry") or 0),
                           sl_pct, tp_pct, candles, timeout_h=timeout_h)
        if r.get("status") in CLOSED_STATUSES:
            net = apply_costs(float(r.get("pnl_pct", 0.0)), slip, fee)
            exit_px = float(o.get("tp") or 0) if r["status"] == "TP" \
                else (float(o.get("sl") or 0) if r["status"] == "SL" else float(candles[-1].get("c", o.get("entry") or 0)))
            return {"status": r["status"], "pnl_pct": net, "exit_price": exit_px,
                    "via": "replay", "gross": float(r.get("pnl_pct", 0.0)), "pool": pool}
        # Replay tak menutup (candle kasar/jarang) -> JATUH ke cek spot di bawah.
        # Jangan return OPEN di sini: harga spot yang jebol SL wajib menutup posisi.
    # 2. Fallback harga titik (mark-to-market)
    px = live_price(o["chain"], o["pair_addr"], o.get("token", ""))
    if not px:
        return {"status": "NO_DATA", "pnl_pct": 0.0, "exit_price": 0.0, "via": "spot", "pool": pool}
    timed_out = age_hours(o.get("opened_ts", "")) >= timeout_h
    r = settle(o["entry"], px, sl_pct, tp_pct, timeout_hit=timed_out)
    if r["status"] in CLOSED_STATUSES:
        net = apply_costs(r["pnl_pct"], slip, fee)
        return {"status": r["status"], "pnl_pct": net, "exit_price": px,
                "via": "spot", "gross": r["pnl_pct"], "pool": pool}
    return {"status": "OPEN", "pnl_pct": r["pnl_pct"], "exit_price": px, "via": "mark-to-market", "pool": pool}


def age_hours(opened_ts: str) -> float:
    try:
        dt = datetime.fromisoformat(str(opened_ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # CURRENT_TIMESTAMP = UTC
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 0.0

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--settle", action="store_true")
    ap.add_argument("--timeout-h", type=float, default=None)
    ap.add_argument("--mark-to-market", action="store_true",
                    help="hanya tampilkan nilai kini, jangan tutup posisi")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    con = connect(db_path())
    pstore.init(con)
    wal.init(con)
    slip = float((cfg.get("paper") or {}).get("slippage_pct", 0.5))
    fee = float((cfg.get("paper") or {}).get("fee_pct", 0.2))
    timeout_h = float(args.timeout_h) if args.timeout_h is not None \
        else float((cfg.get("paper") or {}).get("timeout_h", 72))

    if args.list or not (args.settle or args.report):
        opens = pstore.list_open(con)
        if not opens:
            print("Tidak ada posisi paper OPEN.")
        for o in opens:
            print(f"#{o['id']} {o['symbol']} {o['chain']} entry=${o['entry']} SL=${o['sl']} TP=${o['tp']}")
    if args.settle:
        n = 0
        for o in pstore.list_open(con):
            # M4: biaya per posisi mengikuti likuiditas entry (token tipis
            # bayar slippage lebih mahal, bukan flat 0.5%).
            try:
                _liq = None
                _sig = con.execute("SELECT payload FROM signals WHERE id=?",
                                   (o.get("signal_id", 0) or 0,)).fetchone()
                if _sig and _sig[0]:
                    import json as _json
                    _liq = ((_json.loads(_sig[0]).get("meta") or {}).get("liquidity") or {}).get("liquidity_usd")
                _slip, _fee = effective_costs(_liq, slip, fee, cfg)
            except Exception:
                _slip, _fee = slip, fee
            r = settle_position(o, cfg, timeout_h, _slip, _fee, con)
            if r.get("pool"):
                pstore.set_pool(con, o["id"], r["pool"])
            if r["status"] in CLOSED_STATUSES and not args.mark_to_market:
                pstore.close_position(con, o["id"], r["exit_price"], r["pnl_pct"], r["status"])
                fed = wal.attribute_token_outcome(con, o.get("token", ""), r["pnl_pct"] > 0, r["pnl_pct"]) if o.get("token") else 0
                print(f"- closed #{o['id']} {o['symbol']} {r['status']} {r['pnl_pct']}% (via {r['via']}, wallets fed: {fed})")
                n += 1
            elif r["status"] == "NO_DATA":
                print(f"- skip {o['symbol']}: harga/candle tak tersedia")
            else:
                tag = "mtm" if args.mark_to_market else "open"
                print(f"- {tag} #{o['id']} {o['symbol']} {r['pnl_pct']}% (via {r['via']})")
        mode = "MTM saja (tak ada yang ditutup)" if args.mark_to_market else f"timeout {timeout_h}h"
        print(f"Settled {n} posisi ({mode}).")
    if args.report:
        rows = con.execute("SELECT pnl_pct, close_reason, COALESCE(tier,1) FROM paper_positions WHERE status='CLOSED'").fetchall()
        outcomes = [{"status": r[1], "pnl_pct": r[0]} for r in rows]
        rep = summarize(outcomes)
        print("Paper report (semua tier):", json.dumps(rep, indent=2))
        for t in (1, 2):
            to = [{"status": r[1], "pnl_pct": r[0]} for r in rows if r[2] == t]
            if to:
                print(f"Paper report TIER-{t}:", json.dumps(summarize(to), indent=2))
        if rep.get("n", 0) and rep["expectancy"] <= 0:
            print("WARNING: expectancy <= 0 — jangan pakai uang asli, tune config dulu.")

if __name__ == "__main__":
    main()
