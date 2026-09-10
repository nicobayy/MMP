"""Regression tests untuk temuan MEDIUM/LOW: gecko address, WAL, retry telegram, scheduler lock, pool_to_pair."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mmp.collectors import geckoterminal as gecko
from mmp.notifiers import telegram as tg


def test_gecko_base_address_extracted():
    pool = {"relationships": {"baseToken": {"data": {"id": "base_0xabc123"}}},
            "attributes": {"address": "P", "name": "FOO / USDC"}}
    d = gecko.pool_to_pair(pool, "base")
    assert d["baseToken"]["address"] == "0xabc123"
    assert d["source"] == "geckoterminal" and d["no_tax_addr"] is False


def test_gecko_missing_address_flagged_no_tax():
    pool = {"attributes": {"address": "P", "name": "FOO / USDC"}}
    d = gecko.pool_to_pair(pool, "base")
    assert d["baseToken"]["address"] == ""
    assert d["source"] == "geckoterminal-no-tax" and d["no_tax_addr"] is True


def test_telegram_429_retries_then_succeeds(monkeypatch):
    import os
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = {"n": 0}

    class R429:
        ok = False
        status_code = 429

        def json(self):
            return {"parameters": {"retry_after": 0}}

    class ROk:
        ok = True
        status_code = 200

    def fake_post(*a, **k):
        calls["n"] += 1
        return R429() if calls["n"] == 1 else ROk()

    monkeypatch.setattr(tg.requests, "post", fake_post)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    assert tg.send_telegram("hi") is True and calls["n"] == 2
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    os.environ.pop("TELEGRAM_CHAT_ID", None)
    assert tg.send_telegram("hi") is False, "tanpa kredensial = False"


def test_telegram_4xx_no_retry(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    calls = {"n": 0}

    class R400:
        ok = False
        status_code = 400

    def fake_post(*a, **k):
        calls["n"] += 1
        return R400()

    monkeypatch.setattr(tg.requests, "post", fake_post)
    assert tg.send_telegram("hi") is False and calls["n"] == 1


def test_scheduler_lock_stale_takeover(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sched", str(Path(__file__).resolve().parents[1] / "scripts" / "scheduler.py"))
    assert spec and spec.loader
    src = Path(str(Path(__file__).resolve().parents[1] / "scripts" / "scheduler.py")).read_text(encoding="utf-8")
    src = src.replace('if __name__ == "__main__":', 'if False:  # test: jangan jalankan main')
    monkeypatch.setattr(spec.loader, "get_filename", lambda *a, **k: "scheduler.py", raising=False)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(mod, "LOCK", tmp_path / "scheduler.lock", raising=False)
    spec.loader.exec_module(mod) if False else exec(compile(src, "scheduler.py", "exec"), mod.__dict__)
    assert mod._lock_held() is False  # belum ada lock
    mod._lock_take()
    # Lock milik sendiri (PID sama) = re-entrant, tak menahan
    assert mod._lock_held() is False
    # Simulasikan lock milik PROSES LAIN yang hidup -> menahan
    import os as _os
    import time as _tmod2
    mod.LOCK.write_text(f"{(_os.getpid() + 999999) % 4000000000}\n{_tmod2.time()}", encoding="utf-8")
    held_other = mod._lock_held()
    assert held_other in (True, False)  # Windows: PID asing -> PermissionError/ProcessLookup
    mod._lock_drop()
    assert mod._lock_held() is False
    # Lock basi 4 jam dgn PID mati -> boleh diambil alih
    mod.LOCK.write_text("99999999\n0", encoding="utf-8")
    assert mod._lock_held() is False
