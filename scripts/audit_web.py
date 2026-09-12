"""Audit bundle dashboard web/public/data/*.json dari sisi isi (bukan tampilan).

Usage:
  python scripts/audit_web.py [--dir web/public/data]

Cek: file ada + JSON valid, field wajib, mode valid, duplikat (mode,id),
OPEN tanpa SL/TP, CLOSED tanpa hasil, OPEN tua, konsistensi meta vs isi.
Keluar: daftar temuan bernomor. Temuan = aneh/bug, bukan vonis.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SIG_REQ = ("id", "ts", "verdict", "tier", "confidence", "symbol", "chain",
           "token", "pair_addr", "price", "reason", "mode")
POS_REQ = ("id", "symbol", "chain", "token", "pair_addr", "entry", "sl", "tp",
           "status", "mode")


def _load(d: Path, name: str):
    p = d / name
    if not p.exists():
        return None, f"{name} hilang"
    try:
        return json.loads(p.read_text(encoding="utf-8")), ""
    except Exception as e:
        return None, f"{name} bukan JSON valid ({e})"


def _age_h(ts: str) -> float | None:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "web" / "public" / "data"))
    args = ap.parse_args()
    d = Path(args.dir)
    findings: list[str] = []
    n = 0

    def flag(msg: str):
        nonlocal n
        n += 1
        findings.append(f"{n}. {msg}")

    meta, e = _load(d, "meta.json")
    sig, e2 = _load(d, "signals.json")
    pap, e3 = _load(d, "paper.json")
    bat, e4 = _load(d, "batches.json")
    ops, e5 = _load(d, "ops.json")
    for name, err in (("meta", e), ("signals", e2), ("paper", e3),
                      ("batches", e4), ("ops", e5)):
        if err:
            flag(f"ANEH: {err}")

    signals = (sig or {}).get("signals", []) if sig else []
    positions = (pap or {}).get("positions", []) if pap else []

    seen: set[tuple] = set()
    for s in signals:
        if "mode" not in s:
            s["mode"] = "filter"  # export lama pra-P2: frontend juga default filter
        miss = [k for k in SIG_REQ if k not in s]
        if miss:
            flag(f"ANEH: sinyal id={s.get('id')} kurang field {miss}")
        key = (s.get("mode", "?"), s.get("id"))
        if key in seen:
            flag(f"BUG: duplikat sinyal mode={key[0]} id={key[1]} (ID tabrakan antar-DB?)")
        seen.add(key)
        if s.get("mode") not in ("filter", "sniper"):
            flag(f"ANEH: sinyal id={s.get('id')} mode={s.get('mode')!r} tak dikenal")
        if s.get("verdict") not in ("PASS", "REJECT"):
            flag(f"ANEH: sinyal id={s.get('id')} verdict={s.get('verdict')!r}")
        try:
            c = float(s.get("confidence", -1))
            if not 0 <= c <= 100:
                flag(f"ANEH: sinyal id={s.get('id')} confidence={s.get('confidence')}")
        except (TypeError, ValueError):
            flag(f"ANEH: sinyal id={s.get('id')} confidence non-angka")

    sig_ids = {(s.get("mode", "filter"), s.get("id")) for s in signals}
    for p in positions:
        if "mode" not in p:
            p["mode"] = "filter"  # export lama pra-P2
        miss = [k for k in POS_REQ if k not in p]
        if miss:
            flag(f"ANEH: posisi id={p.get('id')} kurang field {miss}")
        if p.get("mode") not in ("filter", "sniper"):
            flag(f"ANEH: posisi id={p.get('id')} mode={p.get('mode')!r} tak dikenal")
        if p.get("status") == "OPEN":
            if not p.get("entry") or not p.get("sl") or not p.get("tp"):
                flag(f"BUG: posisi OPEN id={p.get('id')} {p.get('symbol')} tanpa entry/SL/TP")
            age = _age_h(str(p.get("opened_ts") or ""))
            lim = 6 if (p.get("mode") or "") == "sniper" else 72
            if age is not None and age > lim + 1:
                flag(f"ANEH: posisi OPEN id={p.get('id')} {p.get('symbol')} umur {age:.1f}h "
                     f"> timeout {lim}h (settle macet? cek log paper --settle)")
        elif p.get("status") == "CLOSED":
            if p.get("pnl_pct") is None or not p.get("close_reason"):
                flag(f"ANEH: posisi CLOSED id={p.get('id')} tanpa pnl/alasan")
        else:
            flag(f"ANEH: posisi id={p.get('id')} status={p.get('status')!r}")
        if (p.get("mode", "filter"), p.get("signal_id")) not in sig_ids and p.get("signal_id"):
            flag(f"INFO: posisi id={p.get('id')} signal_id={p.get('signal_id')} "
                 f"tak ada di feed 1000 terakhir (wajar bila sinyal lama)")

    if meta:
        if meta.get("n_signals") != len(signals):
            flag(f"ANEH: meta n_signals={meta.get('n_signals')} tapi isi {len(signals)}")
        if meta.get("n_pass") != sum(1 for s in signals if s.get("verdict") == "PASS"):
            flag("ANEH: meta n_pass tak cocok hitungan isi")

    print(f"=== AUDIT WEB ({d}) ===")
    print(f"sinyal={len(signals)} posisi={len(positions)} temuan={n}")
    for f in findings:
        print(f"- {f}")
    if not findings:
        print("Bersih: tidak ada aneh/bug di data dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
