"""Scheduler MMP: scan berkala + Telegram + paper auto-open.
Usage: python scripts/scheduler.py --interval-min 60 --limit 5 --chains solana,base --notify --paper
Berhentikan dengan Ctrl+C. Untuk 24/7 pakai Windows Task Scheduler (lihat README).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LOCK = ROOT / "data" / "scheduler.lock"


def _lock_file(tag: str | None = None) -> Path:
    """Lock per-mode agar filter (60m) + sniper (1m) tidak saling blokir.
    Tag dari --lock-tag / MMP_DB / --config (basename). Default = lock lama."""
    if tag:
        safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in tag)[:40] or "x"
        return ROOT / "data" / f"scheduler-{safe}.lock"
    try:
        import os
        db = os.getenv("MMP_DB", "") or ""
        if db and db != "data/mmp.db":
            safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in Path(db).stem)[:40] or "x"
            return ROOT / "data" / f"scheduler-{safe}.lock"
    except Exception:
        pass
    return LOCK


def _lock_held(lock: Path | None = None) -> bool:
    """Overlap-guard: ronde sebelumnya belum selesai -> lewati ronde ini.

    Lock = file berisi PID + timestamp. Pemilik SENDIRI (PID sama) dianggap
    tidak-menahan (re-entrant aman untuk test). Basi (>3 jam) atau PID mati
    dianggap yatim dan boleh diambil alih agar tak macet selamanya.
    """
    lk = lock or LOCK
    try:
        if not lk.exists():
            return False
        import os
        pid_s, ts_s = (lk.read_text(encoding="utf-8") + "\n0").splitlines()[:2]
        try:
            if int(pid_s or 0) == os.getpid():
                return False  # lock milik sendiri (mis. test) -> bukan halangan
        except Exception:
            pass
        age = time.time() - float(ts_s or 0)
        if age > 3 * 3600:
            return False  # basi: pemilik kemungkinan mati
        try:
            os.kill(int(pid_s or 0), 0)  # cek PID hidup (Windows: PermissionError = hidup)
        except ProcessLookupError:
            return False  # PID mati -> lock yatim
        except PermissionError:
            return True  # hidup tapi milik proses lain
        except Exception:
            return True  # tak bisa pastikan -> anggap sibuk (aman)
        return True
    except Exception:
        return False


def _lock_take(lock: Path | None = None) -> None:
    lk = lock or LOCK
    try:
        lk.parent.mkdir(parents=True, exist_ok=True)
        import os
        lk.write_text(f"{os.getpid()}\n{time.time()}", encoding="utf-8")
    except Exception:
        pass


def _lock_drop(lock: Path | None = None) -> None:
    lk = lock or LOCK
    try:
        lk.unlink()
    except Exception:
        pass

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-min", type=int, default=60)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--chains", default="solana,base")
    ap.add_argument("--notify", action="store_true", default=True)
    ap.add_argument("--no-notify", dest="notify", action="store_false")
    ap.add_argument("--paper", action="store_true", default=True)
    ap.add_argument("--no-paper", dest="paper", action="store_false")
    ap.add_argument("--rounds", type=int, default=0, help="0 = selamanya")
    ap.add_argument("--config", default=None, help="Config yaml (sniper pakai config/mmp_sniper.yaml)")
    ap.add_argument("--lock-tag", default=None, help="Tag lock (default dari MMP_DB agar filter+sniper tak rebutan)")
    ap.add_argument("--export-web", action="store_true", default=True,
                    help="Export JSON dashboard web/ tiap akhir round (default on)")
    ap.add_argument("--no-export-web", dest="export_web", action="store_false")
    args = ap.parse_args()
    lock = _lock_file(args.lock_tag or args.config and Path(args.config).stem)
    n = 0
    print(f"Scheduler tiap {args.interval_min}m | chains={args.chains} | notify={args.notify} | paper={args.paper} | cfg={args.config or 'default'}")
    try:
        while True:
            from mmp.safety import is_killed
            if is_killed():
                print("STOP: KILL SWITCH aktif. Scheduler berhenti.")
                break
            if _lock_held(lock):
                print("SKIP: ronde sebelumnya belum selesai (lock). Tidur sampai ronde berikut.")
            else:
                _lock_take(lock)
                try:
                    n += 1
                    print(f"\n===== ROUND {n} =====")
                    cmd = [sys.executable, "-u", "scripts/run_scan.py", "--top-boosts", "--limit", str(args.limit), "--chains", args.chains]
                    if args.config:
                        cmd += ["--config", args.config]
                    if args.notify:
                        cmd.append("--notify")
                    if args.paper:
                        cmd.append("--paper")
                    subprocess.run(cmd, cwd=ROOT)
                    subprocess.run([sys.executable, "-u", "scripts/paper.py", "--settle"], cwd=ROOT)
                    if args.export_web:
                        try:
                            subprocess.run([sys.executable, "-u", "scripts/export_json.py"], cwd=ROOT)
                        except Exception as e:
                            print(f"export web skip ({e})")
                    if args.rounds and n >= args.rounds:
                        break
                finally:
                    _lock_drop(lock)
                    if args.rounds and n >= args.rounds:
                        break
            else_sleep = args.interval_min * 60
            # Jitter kecil agar tak tabrakan dgn cron tetangga tiap jam tepat
            import random as _r
            time.sleep(else_sleep + _r.uniform(0, 30))
    except KeyboardInterrupt:
        print("\nScheduler dihentikan (Ctrl+C).")
    finally:
        try:
            _lock_drop(lock)
        except Exception:
            pass

if __name__ == "__main__":
    main()
