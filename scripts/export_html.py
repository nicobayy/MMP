"""Export dashboard statis (tanpa install streamlit): python scripts/export_html.py"""
from __future__ import annotations

import html
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path


def main():
    db = db_path()
    out = ROOT / "data" / "dashboard.html"
    try:
        con = sqlite3.connect(db)
        rows = con.execute("SELECT id, ts, verdict, symbol, chain, price, confidence, reason FROM signals ORDER BY id DESC LIMIT 200").fetchall()
        con.close()
    except Exception as e:
        print(f"DB belum siap ({e})")
        return
    trs = "\n".join(
        f"<tr><td>{r[0]}</td><td>{html.escape(str(r[1]))}</td><td>{html.escape(str(r[2]))}</td>"
        f"<td>{html.escape(str(r[3]))}</td><td>{html.escape(str(r[4]))}</td><td>{r[5]}</td><td>{r[6]}</td>"
        f"<td>{html.escape(str(r[7] or ''))[:160]}</td></tr>" for r in rows)
    out.write_text(f"""<!doctype html><meta charset=utf-8><title>MMP Dashboard</title>
<style>body{{font-family:system-ui;background:#0b0e14;color:#e6edf3;padding:24px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #30363d;padding:6px 8px;font-size:13px}}th{{background:#161b22}}</style>
<h1>MMP — Melok Melok Profit ({len(rows)} sinyal)</h1>
<p>Solana prioritas • multi-chain • konservatif</p>
<table><tr><th>ID</th><th>Waktu</th><th>Verdict</th><th>Symbol</th><th>Chain</th><th>Price</th><th>Conf</th><th>Reason</th></tr>{trs}</table>""", encoding="utf-8")
    print(f"OK -> {out} ({len(rows)} rows). Buka file ini di browser.")

if __name__ == "__main__":
    main()
