"""MMP LIVE — satu perintah untuk semuanya, 24/7 di VPS.

Menjalankan sekaligus dalam satu proses:
  1. Preflight (python/config/DB/kunci/.env)
  2. Settle paper awal + export JSON dashboard awal
  3. Dashboard web/ (static server :--port, tanpa Python saat viewing)
  4. Loop scheduler: scan -> notify -> paper -> settle -> export (per round)

Usage (Linux VPS):
  python scripts/live.py --chains solana,base --port 8080
  Lebih detail: --interval-min 60 --limit 5 --rounds 0 (= selamanya)
  Untuk autostart: lihat deploy/mmp.service (systemd).

Berhenti: Ctrl+C / SIGTERM (server + loop dimatikan rapi).
"""
from __future__ import annotations

import argparse
import functools
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def fail(msg: str, code: int = 2) -> None:
    print(f"ABORT: {msg}", flush=True)
    raise SystemExit(code)


def preflight(args) -> dict:
    """Cek prasyarat. Return info dashboard. Fatal -> abort, non-fatal -> warn."""
    if sys.version_info < (3, 12):
        fail(f"butuh Python >=3.12, dapat {sys.version.split()[0]}")
    try:
        from mmp.config import db_path, load_config
    except Exception as e:
        fail(f"import engine gagal ({e}). Jalankan pip install -r requirements.txt dulu.")
    try:
        cfg = load_config(args.config)
    except Exception as e:
        fail(f"config tidak valid ({e})")
    try:
        from mmp.storage.store import connect
        con = connect(db_path())
        con.execute("SELECT 1").fetchone()
        con.close()
    except Exception as e:
        fail(f"DB tak bisa dibuka ({e})")
    # Kunci: warning saja (sistem tetap jalan, grade BLIND) agar satu perintah
    # tak mati di VPS hanya karena satu key belum diisi.
    missing = [k for k in ("HELIUS_API_KEY", "BIRDEYE_API_KEY") if not os.getenv(k, "").strip()]
    if missing:
        print(f"WARN: tanpa {', '.join(missing)} -> Solana BLIND (jalan terus, bukan abort).", flush=True)
    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or not os.getenv("TELEGRAM_CHAT_ID", "").strip():
        print("WARN: Telegram tak dikonfigurasi -> alert di-skip (sinyal tetap log + paper).", flush=True)
    from mmp import safety as guard
    if guard.is_killed():
        fail("KILL SWITCH aktif (data/STOP ada). Matikan: python scripts/killswitch.py --off")
    dist = ROOT / "web" / "dist"
    if not (dist / "index.html").exists():
        if args.build:
            print("Dashboard belum di-build -> npm run build sekarang...", flush=True)
            r = subprocess.run(["npm", "run", "build"], cwd=ROOT / "web")
            if r.returncode != 0 or not (dist / "index.html").exists():
                fail("npm run build gagal. Build manual: cd web && npm install && npm run build")
        else:
            fail("web/dist hilang. Jalankan sekali: cd web && npm install && npm run build (atau tambah --build)")
    return {"dist": dist, "t1": float((cfg.get("signal") or {}).get("min_confidence", 85))}


class _Handler(SimpleHTTPRequestHandler):
    """Static server: JSON data tak boleh di-cache agar UI selalu segar."""

    def end_headers(self):
        try:
            if self.path.split("?")[0].endswith(".json"):
                self.send_header("Cache-Control", "no-store, max-age=0")
            else:
                self.send_header("Cache-Control", "public, max-age=300")
        except Exception:
            pass
        super().end_headers()

    def log_message(self, *a):
        pass  # jangan banjiri log VPS per polling 45 detik


def start_dashboard(dist: Path, port: int) -> ThreadingHTTPServer:
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port),
                                  functools.partial(_Handler, directory=str(dist)))
    except OSError as e:
        fail(f"port {port} tak bisa dipakai ({e}). Ganti via --port.")
    t = threading.Thread(target=srv.serve_forever, name="mmp-dash", daemon=True)
    t.start()
    print(f"Dashboard: http://0.0.0.0:{port}/ (bind semua interface; batasi via firewall/reverse-proxy)",
          flush=True)
    return srv


def run_once(exe: str, *argv: str) -> None:
    try:
        subprocess.run([exe, "-u", *argv], cwd=ROOT)
    except Exception as e:
        print(f"skip {' '.join(argv)} ({e})", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="MMP live 24/7: dashboard + scheduler loop")
    ap.add_argument("--chains", default="solana,base")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--interval-min", type=int, default=60)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--rounds", type=int, default=0, help="0 = selamanya (24/7)")
    ap.add_argument("--notify", action="store_true", default=True)
    ap.add_argument("--no-notify", dest="notify", action="store_false")
    ap.add_argument("--paper", action="store_true", default=True)
    ap.add_argument("--no-paper", dest="paper", action="store_false")
    ap.add_argument("--build", action="store_true", help="npm run build bila web/dist hilang")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    info = preflight(args)
    print(f"MMP LIVE | chains={args.chains} limit={args.limit} "
          f"interval={args.interval_min}m port={args.port} T1>={info['t1']:.0f}", flush=True)
    run_once(sys.executable, "scripts/paper.py", "--settle")
    run_once(sys.executable, "scripts/export_json.py")
    srv = start_dashboard(info["dist"], args.port)

    # Pinjam loop scheduler apa adanya (lock, jitter, settle+export per round).
    sys.argv = [sys.argv[0], "--interval-min", str(args.interval_min),
                "--limit", str(args.limit), "--chains", args.chains,
                "--rounds", str(args.rounds)]
    if args.notify:
        sys.argv.append("--notify")
    else:
        sys.argv.append("--no-notify")
    if args.paper:
        sys.argv.append("--paper")
    else:
        sys.argv.append("--no-paper")
    try:
        from scripts.scheduler import main as sched_main  # type: ignore
    except ImportError:
        sys.path.insert(0, str(ROOT / "scripts"))
        from scheduler import main as sched_main  # type: ignore
    try:
        sched_main()
    except KeyboardInterrupt:
        print("\nMMP LIVE dihentikan (Ctrl+C).")
    finally:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass
        print("Dashboard dimatikan. Bye.")


if __name__ == "__main__":
    main()
