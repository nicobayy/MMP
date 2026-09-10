"""Entry points console (`mmp-scan`, `mmp-paper`, ...) setelah `pip install -e .`.
Thin dispatcher ke scripts/*.py yang sudah ada — tanpa duplikasi logika.
scripts/ tetap bisa jalan langsung via `python scripts/*.py` (sys.path lokal).
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

def _run(name: str):
    # Dipasang sebagai console script: teruskan argv apa adanya ke script.
    runpy.run_path(str(SCRIPTS / name), run_name="__main__")

def scan(): _run("run_scan.py")
def paper(): _run("paper.py")
def backtest(): _run("backtest.py")
def scheduler(): _run("scheduler.py")
def callout(): _run("add_callout.py")
def wallets():
    _run("record_outcome.py")


def whale_watch():
    _run("whale_watch.py")
def telegram_test(): _run("test_telegram.py")
def killswitch(): _run("killswitch.py")

def main():
    print("mmp commands: mmp-scan, mmp-paper, mmp-backtest, mmp-scheduler,")
    print("  mmp-callout, mmp-wallets, mmp-telegram-test, mmp-killswitch")
    return 0

if __name__ == "__main__":
    sys.exit(main())
