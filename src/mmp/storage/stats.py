"""Statistik cakupan data per batch scan (instrumentasi, bukan scoring).
Tujuan: UKUR bottleneck cakupan sumber data sebelum memutuskan menambah
sumber baru (mis. GoPlus sebagai fallback honeypot.is). Aturan main:
<10% BLIND-akibat-sumber = tak layak tambah kompleksitas; >50% = bottleneck
nyata yang menjustifikasi fallback berlapis (tetap fail-closed).
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS batch_stats(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  n INTEGER DEFAULT 0,
  complete INTEGER DEFAULT 0,
  partial INTEGER DEFAULT 0,
  blind INTEGER DEFAULT 0,
  hp_ok INTEGER DEFAULT 0,
  hp_no_tax INTEGER DEFAULT 0,
  hp_fail INTEGER DEFAULT 0
);
"""

def init(con: sqlite3.Connection):
    con.execute(SCHEMA)
    con.commit()

def summarize_batch(items: list[dict]) -> dict:
    """Agregasi murni. items: [{grade: COMPLETE|PARTIAL|BLIND,
    hp: ok|no_tax|fail|na}]. Status hp ditentukan pemanggil dari enrichment
    mentah (bukan dari note string) agar klasifikasi jujur:
    - ok: honeypot.is merespons + tax diketahui
    - no_tax: "berhasil" tapi simulasi kosong (tax None)
    - fail: error/timeout/unsupported (gagal keras)
    - na: bukan chain EVM (Solana tak memakai honeypot.is)
    """
    st = {"n": 0, "complete": 0, "partial": 0, "blind": 0,
          "hp_ok": 0, "hp_no_tax": 0, "hp_fail": 0}
    for it in items:
        st["n"] += 1
        g = str(it.get("grade", "?")).upper()
        if g in ("COMPLETE", "PARTIAL", "BLIND"):
            st[g.lower()] += 1
        h = str(it.get("hp", "na")).lower()
        if h in ("ok", "no_tax", "fail"):
            st[f"hp_{h}"] += 1
    return st

def save_batch(con: sqlite3.Connection, st: dict) -> int:
    init(con)
    cur = con.execute(
        "INSERT INTO batch_stats(n, complete, partial, blind, hp_ok, hp_no_tax, hp_fail)"
        " VALUES(?,?,?,?,?,?,?)",
        (st.get("n", 0), st.get("complete", 0), st.get("partial", 0), st.get("blind", 0),
         st.get("hp_ok", 0), st.get("hp_no_tax", 0), st.get("hp_fail", 0)))
    con.commit()
    return int(cur.lastrowid or 0)

def coverage_report(con: sqlite3.Connection) -> dict:
    """Agregat historis untuk keputusan tambah-sumber-atau-tidak."""
    init(con)
    row = con.execute("SELECT COUNT(*), COALESCE(SUM(n),0), COALESCE(SUM(complete),0),"
                      " COALESCE(SUM(partial),0), COALESCE(SUM(blind),0),"
                      " COALESCE(SUM(hp_ok),0), COALESCE(SUM(hp_no_tax),0), COALESCE(SUM(hp_fail),0)"
                      " FROM batch_stats").fetchone() or (0, 0, 0, 0, 0, 0, 0, 0)
    batches, n, c, p, b, ok, notax, fail = (int(x or 0) for x in row)
    evm = ok + notax + fail
    return {"batches": batches, "signals": n,
            "complete_pct": round(c / n * 100, 1) if n else 0.0,
            "partial_pct": round(p / n * 100, 1) if n else 0.0,
            "blind_pct": round(b / n * 100, 1) if n else 0.0,
            "hp_tax_ok_pct": round(ok / evm * 100, 1) if evm else 0.0,
            "hp_gap_pct": round((notax + fail) / evm * 100, 1) if evm else 0.0}
