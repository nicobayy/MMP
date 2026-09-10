"""Kill switch MMP.
Usage:
  python scripts/killswitch.py --on    # hentikan semua scan/scheduler
  python scripts/killswitch.py --off   # nyalakan lagi
  python scripts/killswitch.py --status
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.safety import stop_file, is_killed  # noqa: E402
from mmp.notifiers.telegram import send_telegram  # noqa: E402

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", action="store_true")
    ap.add_argument("--off", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    f = stop_file()
    if args.on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("STOP", encoding="utf-8")
        send_telegram("🛑 <b>MMP KILL SWITCH ON</b>: scan & alert dihentikan.")
        print("KILL SWITCH ON.")
    elif args.off:
        try:
            f.unlink()
        except FileNotFoundError:
            pass
        print("KILL SWITCH OFF.")
    else:
        print("KILLED" if is_killed() else "RUNNING")

if __name__ == "__main__":
    main()
