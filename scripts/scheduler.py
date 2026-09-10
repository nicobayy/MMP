"""Scheduler MMP: scan berkala + Telegram + paper auto-open.
Usage: python scripts/scheduler.py --interval-min 60 --limit 5 --chains solana,base --notify --paper
Berhentikan dengan Ctrl+C. Untuk 24/7 pakai Windows Task Scheduler (lihat README).
"""
from __future__ import annotations
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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
    args = ap.parse_args()
    n = 0
    print(f"Scheduler tiap {args.interval_min}m | chains={args.chains} | notify={args.notify} | paper={args.paper}")
    while True:
        n += 1
        print(f"\n===== ROUND {n} =====")
        cmd = [sys.executable, "scripts/run_scan.py", "--top-boosts", "--limit", str(args.limit), "--chains", args.chains]
        if args.notify:
            cmd.append("--notify")
        if args.paper:
            cmd.append("--paper")
        subprocess.run(cmd, cwd=ROOT)
        subprocess.run([sys.executable, "scripts/paper.py", "--settle"], cwd=ROOT)
        if args.rounds and n >= args.rounds:
            break
        time.sleep(args.interval_min * 60)

if __name__ == "__main__":
    main()
