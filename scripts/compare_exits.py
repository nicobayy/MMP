"""Bandingkan profil exit A (config aktif) vs profil B (override CLI) di atas
posisi paper CLOSED yang sama + candle yang sama. Tanpa network tambahan
selain yang sudah dilakukan settle (candle dibaca dari cache DB).

Usage (di VPS):
  MMP_DB=data/mmp_sniper.db MMP_CONFIG=config/mmp_sniper.yaml \
    venv/bin/python scripts/compare_exits.py --tp2 100 --act2 8 --cb2 4
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from paper import settle_position  # noqa: E402

from mmp.backtest.engine import effective_costs  # noqa: E402
from mmp.config import db_path, load_config  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _liq_of(con, signal_id: int):
    try:
        row = con.execute("SELECT payload FROM signals WHERE id=?", (signal_id,)).fetchone()
        if row and row[0]:
            import json as _json
            return ((_json.loads(row[0]).get("meta") or {}).get("liquidity") or {}).get("liquidity_usd")
    except Exception:
        pass
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Adu profil exit di posisi CLOSED yang sama")
    ap.add_argument("--tp2", type=float, default=100.0, help="TP profil B (%)")
    ap.add_argument("--act2", type=float, default=8.0, help="aktivasi trailing B (%)")
    ap.add_argument("--cb2", type=float, default=4.0, help="callback trailing B (%)")
    args = ap.parse_args()

    cfg = load_config()
    con = connect(db_path())
    paper_cfg = cfg.get("paper") or {}
    timeout_h = float(paper_cfg.get("timeout_h", 72))
    slip0 = float(paper_cfg.get("slippage_pct", 0.5))
    fee0 = float(paper_cfg.get("fee_pct", 0.2))

    cfgB = copy.deepcopy(cfg)
    cfgB["position"] = dict(cfg.get("position") or {})
    cfgB["position"]["default_take_profit_pct"] = float(args.tp2)
    cfgB["paper"] = dict(paper_cfg)
    cfgB["paper"]["trailing"] = {"enabled": True, "activation_pct": float(args.act2),
                                 "callback_pct": float(args.cb2)}

    rows = con.execute(
        "SELECT id, symbol, chain, token, pair_addr, entry, sl, tp, signal_id,"
        " opened_ts, close_reason, pnl_pct FROM paper_positions"
        " WHERE status='CLOSED' AND entry > 0 ORDER BY id").fetchall()
    if not rows:
        print("Belum ada posisi CLOSED. Tunggu settle dulu.")
        return
    print(f"Profil A = config aktif | Profil B = TP {args.tp2}% + trail {args.act2}/{args.cb2}")
    totA = totB = 0.0
    nA = nB = 0
    for (pid, sym, ch, tok, pair, entry, sl, tp, sid, opened, reason, pnl) in rows:
        o = {"chain": ch, "token": tok, "pair_addr": pair, "entry": entry,
             "sl": sl, "tp": tp, "opened_ts": opened}
        s, f = effective_costs(_liq_of(con, sid or 0), slip0, fee0, cfg)
        rA = settle_position(o, cfg, timeout_h, s, f, con)
        oB = dict(o, tp=(entry or 0) * (1 + float(args.tp2) / 100))
        s2, f2 = effective_costs(_liq_of(con, sid or 0), slip0, fee0, cfgB)
        rB = settle_position(oB, cfgB, timeout_h, s2, f2, con)
        a = f"{rA['status']} {rA['pnl_pct']}%"
        b = f"{rB['status']} {rB['pnl_pct']}%"
        if rA["status"] in ("TP", "SL", "TIMEOUT", "TRAIL"):
            totA += float(rA["pnl_pct"])
            nA += 1
        if rB["status"] in ("TP", "SL", "TIMEOUT", "TRAIL"):
            totB += float(rB["pnl_pct"])
            nB += 1
        print(f"#{pid} {sym}: aktual={reason} {pnl}% | A={a} ({rA['via']}) | B={b} ({rB['via']})")
    print(f"Total A: {round(totA, 2)}% dari {nA} | Total B: {round(totB, 2)}% dari {nB} | n={len(rows)}")


if __name__ == "__main__":
    main()
