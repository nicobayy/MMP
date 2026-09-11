"""Export data dashboard web: SQLite -> web/public/data/*.json.

Kontrak untuk frontend di web/ (Vite React, tanpa Python saat viewing):
  meta.json    {exported_at, t1, t2, counts}
  signals.json {exported_at, signals: [{id,ts,verdict,tier,confidence,threshold,
                symbol,chain,token,pair_addr,price,dex,reason,vetoes,scores,
                grade,dual_ok,dual_note,mcap,liq,url,entry,sl,tp,sl_pct,tp_pct,
                rr,size_usd,risk_pct,checklist}]}
  paper.json   {exported_at, positions: [{id,signal_id,symbol,chain,token,pair_addr,
                entry,sl,tp,risk_pct,tier,status,opened_ts,closed_ts,exit_price,
                pnl_pct,close_reason}]}
  batches.json {exported_at, batches: [{id,ts,n,complete,partial,blind,
                hp_ok,hp_no_tax,hp_fail}]}
  ops.json     {exported_at,last_scan,n_today,n_total,whale_last,whale_26h,
                n_open,n_closed,kol7,killed,db_size}

Usage:
  python scripts/export_json.py [--out web/public/data] [--limit 1000]
  Dipanggil otomatis tiap akhir round scheduler (best-effort).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mmp.config import db_path  # noqa: E402
from mmp.storage.store import connect  # noqa: E402

try:
    from mmp.config import load_config
except Exception:  # pragma: no cover
    def load_config(path=None):  # type: ignore[no-redef]
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _loads(p: str | None) -> dict:
    try:
        d = json.loads(p or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _thresholds() -> tuple[float, float]:
    try:
        cfg = load_config()
        t1 = float((cfg.get("signal") or {}).get("min_confidence", 85))
        t2 = float((cfg.get("tiers") or {}).get("tier2_min", 75))
        return t1, t2
    except Exception:
        return 85.0, 75.0


def _flatten_signal(row: tuple) -> dict:
    sid, ts, verdict, symbol, chain, token, pair_addr, price, conf, reason, payload = row
    d = _loads(payload)
    meta = d.get("meta") or {}
    liq = meta.get("liquidity") or {}
    dual = meta.get("dual") or {}
    plan = d.get("plan") or {}
    try:
        tier = int(d.get("tier", 1 if d.get("verdict") == "PASS" else 0))
    except Exception:
        tier = 0
    return {
        "id": sid, "ts": ts, "verdict": verdict, "tier": tier,
        "confidence": conf, "threshold": d.get("threshold"),
        "symbol": symbol, "chain": chain, "token": token, "pair_addr": pair_addr,
        "price": price, "dex": d.get("dex"), "reason": reason,
        "vetoes": d.get("vetoes") or [], "scores": d.get("scores") or {},
        "grade": str(meta.get("data_grade", "?")),
        "dual_ok": bool(dual.get("ok")), "dual_note": str(dual.get("note", "-")),
        "mcap": meta.get("mcap"), "liq": liq.get("liquidity_usd"),
        "url": meta.get("url", ""),
        "entry": plan.get("entry"), "sl": plan.get("stop_loss"),
        "tp": plan.get("take_profit"), "sl_pct": plan.get("sl_pct"),
        "tp_pct": plan.get("tp_pct"), "rr": plan.get("RR"),
        "size_usd": plan.get("size_usd"), "risk_pct": plan.get("risk_pct"),
        "checklist": meta.get("checklist") or [],
    }


def _write_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def export_all(out_dir: Path, limit: int = 1000, paper_limit: int = 500) -> dict:
    db = db_path()
    con = connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, ts, verdict, symbol, chain, token, pair_addr, price,"
            " confidence, reason, payload FROM signals ORDER BY id DESC LIMIT ?",
            (int(limit),)).fetchall()
        try:
            positions = [dict(r) for r in con.execute(
                "SELECT id, signal_id, symbol, chain, token, pair_addr, entry, sl, tp,"
                " risk_pct, opened_ts, closed_ts, status, exit_price, pnl_pct,"
                " close_reason, COALESCE(tier,1) AS tier FROM paper_positions"
                " ORDER BY id DESC LIMIT ?", (int(paper_limit),)).fetchall()]
        except Exception:
            positions = []
        try:
            batches = [dict(r) for r in con.execute(
                "SELECT id, ts, n, complete, partial, blind, hp_ok, hp_no_tax, hp_fail"
                " FROM batch_stats ORDER BY id DESC LIMIT 100").fetchall()]
        except Exception:
            batches = []

        def _one(q: str):
            try:
                r = con.execute(q).fetchone()
                return r[0] if r else None
            except Exception:
                return None

        ops = {
            "last_scan": _one("SELECT MAX(ts) FROM signals"),
            "n_today": _one("SELECT COUNT(*) FROM signals WHERE date(ts)=date('now')") or 0,
            "n_total": _one("SELECT COUNT(*) FROM signals") or 0,
            "whale_last": _one("SELECT MAX(ts) FROM whale_buys"),
            "whale_26h": _one("SELECT COUNT(*) FROM whale_buys"
                               " WHERE ts >= datetime('now','-26 hours')") or 0,
            "n_open": _one("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'") or 0,
            "n_closed": _one("SELECT COUNT(*) FROM paper_positions WHERE status='CLOSED'") or 0,
            "kol7": _one("SELECT COUNT(*) FROM kol_callouts"
                         " WHERE ts >= datetime('now','-7 days')") or 0,
        }
    finally:
        try:
            con.close()
        except Exception:
            pass

    t1, t2 = _thresholds()
    now = _now_iso()
    try:
        killed = Path(os.getenv("MMP_STOP", "data/STOP")).exists()
    except Exception:
        killed = False
    try:
        db_size = Path(db).stat().st_size if Path(db).exists() else 0
    except Exception:
        db_size = 0

    signals = [_flatten_signal(r) for r in rows]
    n_pass = sum(1 for s in signals if s["verdict"] == "PASS")
    payloads = {
        "meta.json": {"exported_at": now, "t1": t1, "t2": t2,
                      "n_signals": len(signals), "n_pass": n_pass,
                      "n_open": ops["n_open"], "n_closed": ops["n_closed"]},
        "signals.json": {"exported_at": now, "signals": signals},
        "paper.json": {"exported_at": now, "positions": positions},
        "batches.json": {"exported_at": now, "batches": batches},
        "ops.json": {"exported_at": now, **ops, "killed": killed, "db_size": db_size},
    }
    out = Path(out_dir)
    for name, obj in payloads.items():
        _write_atomic(out / name, obj)
    # Mirror ke web/dist/data bila frontend sudah di-build: dist adalah snapshot
    # public/ saat build, jadi produksi (preview/nginx) perlu salinan segar.
    # mkdir sendiri: di clone segar, data/*.json di-ignore git sehingga
    # dist/data tak ada saat build -> tanpa ini mirror selalu skip.
    dist_data = ROOT / "web" / "dist" / "data"
    mirrored = False
    if (ROOT / "web" / "dist").is_dir():
        try:
            dist_data.mkdir(parents=True, exist_ok=True)
            for name, obj in payloads.items():
                _write_atomic(dist_data / name, obj)
            mirrored = True
        except Exception:
            mirrored = False
    return {"out": str(out), "signals": len(signals), "positions": len(positions),
            "batches": len(batches), "mirrored": mirrored}


def main() -> None:
    ap = argparse.ArgumentParser(description="Export SQLite -> JSON untuk dashboard web/")
    ap.add_argument("--out", default=str(ROOT / "web" / "public" / "data"))
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--paper-limit", type=int, default=500)
    args = ap.parse_args()
    try:
        res = export_all(Path(args.out), args.limit, args.paper_limit)
    except Exception as e:
        print(f"Export gagal ({e})")
        raise SystemExit(1)
    print(f"OK -> {res['out']} "
          f"(signals={res['signals']} positions={res['positions']} batches={res['batches']})")


if __name__ == "__main__":
    main()
