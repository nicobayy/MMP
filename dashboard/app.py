"""MMP Dashboard — baca data/mmp.db, filter PASS/chain, tanpa perlu API key."""
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path  # noqa: E402

st.set_page_config(page_title="MMP — Melok Melok Profit", layout="wide")
st.title("MMP — Melok Melok Profit")
st.caption("Precision-first • Solana prioritas, multi-chain • Konservatif: REJECT banyak itu normal")

@st.cache_data(ttl=15)
def load_df(path: str) -> pd.DataFrame:
    con = sqlite3.connect(path)
    try:
        df = pd.read_sql_query("SELECT id, ts, verdict, symbol, chain, token, pair_addr, price, confidence, reason FROM signals ORDER BY id DESC LIMIT 1000", con)
    except Exception:
        df = pd.DataFrame()
    con.close()
    return df

db = db_path()
df = load_df(db)
if df.empty:
    st.warning(f"Belum ada sinyal di {db}. Jalankan: python scripts/run_scan.py --top-boosts --limit 10")
    st.stop()

c1, c2, c3 = st.columns(3)
with c1:
    verdicts = st.multiselect("Verdict", sorted(df["verdict"].unique().tolist()), default=sorted(df["verdict"].unique().tolist()))
with c2:
    chains = st.multiselect("Chain", sorted(df["chain"].unique().tolist()), default=sorted(df["chain"].unique().tolist()))
with c3:
    min_conf = st.slider("Min confidence", 0, 100, 0)

f = df[df["verdict"].isin(verdicts) & df["chain"].isin(chains) & (df["confidence"] >= min_conf)]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", len(f))
m2.metric("PASS", int((f["verdict"] == "PASS").sum()))
m3.metric("PASS rate (bukan precision)", f"{(f['verdict']=='PASS').mean()*100:.1f}%" if len(f) else "—")
m4.metric("Avg conf", f"{f['confidence'].mean():.1f}" if len(f) else "—")

st.dataframe(f, use_container_width=True, hide_index=True)

sel = st.selectbox("Detail sinyal (id)", f["id"].tolist()[:100] if len(f) else [])
if sel:
    con = sqlite3.connect(db)
    row = con.execute("SELECT payload FROM signals WHERE id=?", (sel,)).fetchone()
    con.close()
    if row:
        d = json.loads(row[0])
        st.subheader(f"{d.get('symbol')} [{d.get('verdict')}] conf={d.get('confidence')}")
        st.json({"scores": d.get("scores"), "vetoes": d.get("vetoes"), "plan": d.get("plan"), "meta": d.get("meta"), "notes": d.get("notes")})
        if (d.get("meta") or {}).get("url"):
            st.link_button("Buka DexScreener", d["meta"]["url"])
