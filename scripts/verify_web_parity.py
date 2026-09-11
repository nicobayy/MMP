"""Verifikasi parity DB vs JSON web (sekali pakai, Threshold T1/T2, counts)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path
from mmp.storage.store import connect

con = connect(db_path())
db_n = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
db_pass = con.execute("SELECT COUNT(*) FROM signals WHERE verdict='PASS'").fetchone()[0]
db_open = con.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'").fetchone()[0]
db_closed = con.execute("SELECT COUNT(*) FROM paper_positions WHERE status='CLOSED'").fetchone()[0]
con.close()

meta = json.loads((ROOT / "web" / "dist" / "data" / "meta.json").read_text())
ops = json.loads((ROOT / "web" / "dist" / "data" / "ops.json").read_text())
sig = json.loads((ROOT / "web" / "dist" / "data" / "signals.json").read_text())
assert meta["n_signals"] == db_n, (meta["n_signals"], db_n)
assert meta["n_pass"] == db_pass, (meta["n_pass"], db_pass)
assert ops["n_total"] == db_n
assert ops["n_open"] == db_open and ops["n_closed"] == db_closed
assert len(sig["signals"]) == db_n
assert meta["t1"] == 85.0 and meta["t2"] == 75.0
print(f"PARITY OK: signals={db_n} pass={db_pass} open={db_open} closed={db_closed}")
