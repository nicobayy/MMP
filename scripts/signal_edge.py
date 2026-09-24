"""Bandingkan fitur sinyal winner vs loser dari payload tersimpan.

Menjawab "apa yang membedakan entry bagus" tanpa menebak ambang:
tarik confidence, liq, overlap trusted, whale buys, top10/top1 dari
payload sinyal tiap posisi CLOSED, agregat per outcome. Beda jauh =
kandidat filter berikutnya. Beda nol = fitur itu tak membedakan.

Usage (di VPS):
  MMP_DB=data/mmp_sniper.db venv/bin/python scripts/signal_edge.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path  # noqa: E402
from mmp.storage.store import connect  # noqa: E402


def _num(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def main() -> None:
    ap = argparse.ArgumentParser(description="Fitur apa membedakan winner?")
    ap.add_argument("--min-n", type=int, default=5)
    args = ap.parse_args()
    con = connect(db_path())
    rows = con.execute(
        "SELECT symbol, pnl_pct, signal_id FROM paper_positions"
        " WHERE status='CLOSED' AND entry > 0").fetchall()
    wins: list[dict] = []
    losses: list[dict] = []
    skipped = 0
    for sym, pnl, sid in rows:
        try:
            prow = con.execute("SELECT payload FROM signals WHERE id=?", (sid,)).fetchone()
            d = json.loads((prow or ["{}"])[0])
        except Exception:
            skipped += 1
            continue
        meta = d.get("meta") or {}
        sm = meta.get("sm") or {}
        liq = meta.get("liquidity") or {}
        feat = {"conf": _num(d.get("confidence")),
                "liq": _num(liq.get("liquidity_usd")),
                "overlap": int(sm.get("trusted_overlap") or 0),
                "whale": int(sm.get("whale_buys") or 0),
                "top10": _num(sm.get("top10_pct"), -1.0),
                "top1": _num(sm.get("top1_pct"), -1.0)}
        (wins if float(pnl or 0) > 0 else losses).append(feat)
    print(f"n={len(rows)} win={len(wins)} loss={len(losses)} skip-tanpa-payload={skipped}")
    if len(wins) < args.min_n or len(losses) < args.min_n:
        print("Belum cukup untuk baca pola. Kumpulkan dulu.")
        return
    for k in ("conf", "liq", "overlap", "whale", "top10", "top1"):
        w = [f[k] for f in wins if f[k] >= 0]
        lo = [f[k] for f in losses if f[k] >= 0]
        if not w or not lo:
            print(f"{k}: data tak tersedia")
            continue
        mw, ml = sum(w) / len(w), sum(lo) / len(lo)
        flag = "  <-- BEDA" if (ml and abs(mw - ml) / max(abs(ml), 1e-9) > 0.3) or (not ml and mw) else ""
        if k == "liq":
            print(f"{k}: win ${mw:,.0f} vs loss ${ml:,.0f}{flag}")
        elif k in ("top10", "top1"):
            print(f"{k}: win {mw:.1f}% vs loss {ml:.1f}%{flag}")
        else:
            print(f"{k}: win {mw:.2f} vs loss {ml:.2f}{flag}")
    print("Baca: baris BEDA = calon filter. Tak ada BEDA = butuh data baru (holder velocity, funder).")


if __name__ == "__main__":
    main()
