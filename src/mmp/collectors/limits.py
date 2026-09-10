"""Batas konkurensi PER SUMBER API (semaphore).
Aturan main: pool thread boleh besar, tapi tiap sumber API dibatasi
sendiri-sendiri agar tak mempercepat kena rate-limit. Dipakai via:

    with limits.guard("helius"):
        ...satu HTTP/RPC call...

Tanpa configure() = tiap sumber max 1000 (praktis unlimited, fail-open).
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Generator

log = logging.getLogger(__name__)

_lock = threading.Lock()
_limits: dict[str, int] = {}
_sems: dict[str, threading.Semaphore] = {}
DEFAULT_MAX = 1000

def configure(limits: dict | None):
    global _limits, _sems
    with _lock:
        _limits = {k: max(1, int(v)) for k, v in (limits or {}).items()}
        _sems = {}

def _sem(source: str) -> threading.Semaphore:
    with _lock:
        sem = _sems.get(source)
        if sem is None:
            sem = threading.Semaphore(_limits.get(source, DEFAULT_MAX))
            _sems[source] = sem
        return sem

@contextmanager
def guard(source: str) -> Generator[None, None, None]:
    sem = _sem(source)
    sem.acquire()
    try:
        yield
    finally:
        sem.release()
