"""Telegram notifier + formatter sinyal. Anti-spam via cooldown per pair."""
from __future__ import annotations

import html
import os

import requests

TIMEOUT = 15

def _esc(x) -> str:
    return html.escape(str(x), quote=False)

def _check_icon(status: str) -> str:
    return {"OK": "✅", "FAIL": "⛔", "WARN": "⚠️"}.get(status, "❔")

def format_checklist(d) -> str:
    items = ((d.get("meta") or {}).get("checklist") or [])
    if not items:
        return ""
    return "Audit: " + " ".join(f"{_check_icon(i.get('status', '?'))}{_esc(i.get('item', '?'))}" for i in items)

def _mode_tag(mode: str) -> tuple[str, str]:
    """(badge, hashtag) per mode agar filter vs sniper langsung beda di chat."""
    if (mode or "filter") == "sniper":
        return "⚡ SNIPER", "#Sniper"
    return "🛡️ FILTER", "#Filter"


def _short_num(x) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    if 0 < v < 0.01:
        return f"${v:.6f}"
    return f"${v:,.4f}"


def format_signal(s, mode: str = "filter") -> str:
    d = s.to_dict() if hasattr(s, "to_dict") else s
    tier = int(d.get("tier", 1 if d.get("verdict") == "PASS" else 0))
    emoji = "✅" if d["verdict"] == "PASS" and tier == 1 else ("🔶" if d["verdict"] == "PASS" else "⛔")
    badge, tag = _mode_tag(mode)
    tier_txt = f"TIER-{tier}" + (" · size 1/2" if tier == 2 else "")
    meta = d.get("meta") or {}
    liq = (meta.get("liquidity") or {}).get("liquidity_usd")
    lines = [
        f"{emoji} <b>{badge} {tier_txt} | {_esc(d['symbol'])} ({_esc(d['chain'])})</b>",
        f"Conf <b>{d['confidence']}</b> (min {d['threshold']}) · {_esc(d['dex'])}",
        f"Harga {_short_num(d['price_usd'])} · MCap {_short_num(meta.get('mcap'))} · Liq {_short_num(liq)}",
    ]
    pl = (d.get("plan") or {})
    if pl:
        lines += [
            f"🎯 Entry {_short_num(pl.get('entry'))}",
            f"🛑 SL {_short_num(pl.get('stop_loss'))} (-{pl.get('sl_pct')}%)",
            f"💰 TP {_short_num(pl.get('take_profit'))} (+{pl.get('tp_pct')}%) · RR {pl.get('RR')}",
        ]
    # Peringatan saja (yang OK tak usah disebut — itu isi 80% kebisingan kemarin).
    warns: list[str] = []
    for it in (meta.get("checklist") or []):
        if it.get("status") in ("FAIL", "WARN") and it.get("item") in ("mint", "freeze", "honeypot", "top10", "dual"):
            warns.append(f"{_check_icon(it.get('status', '?'))} {_esc(it.get('item'))}: {_esc(it.get('detail', ''))}")
    grade = meta.get("data_grade")
    if grade and grade != "COMPLETE":
        warns.append(f"⚠️ data {_esc(grade)} (verifikasi sebagian)")
    for v in (d.get("vetoes") or [])[:2]:
        warns.append(f"⛔ {_esc(v)}")
    if warns:
        lines.append("Perhatian:\n" + "\n".join(f"• {w}" for w in warns[:4]))
    if meta.get("url"):
        lines.append(f"<a href=\"{_esc(meta['url'])}\">Buka chart ↗</a>")
    lines.append(f"#MMP #MelokMelokProfit {tag}")
    return "\n".join(lines)

def format_summary(n_pass: int, n_reject: int, passes: list,
                   mode: str = "filter", n_skip: int = 0) -> str:
    t1 = sum(1 for p in passes if int(p.get("tier", 1)) == 1)
    t2 = sum(1 for p in passes if int(p.get("tier", 1)) == 2)
    badge, _tag = _mode_tag(mode)
    if not passes:
        return ""
    lines = [f"📊 <b>{badge} | PASS={n_pass} (T1={t1} T2={t2}) · SKIP={n_skip}</b>"]
    for p in passes[:10]:
        lines.append(f"{'✅' if int(p.get('tier', 1)) == 1 else '🔶'} [T{int(p.get('tier', 1))}]"
                     f" {_esc(p['symbol'])} conf={p['confidence']} {_short_num(p['price_usd'])}")
    return "\n".join(lines)

def creds() -> tuple[str, str]:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_telegram(text: str, retries: int = 2) -> bool:
    """Kirim pesan Telegram dgn retry + hormati rate-limit 429 (Retry-After).

    Tanpa kredensial -> False (graceful, sinyal tetap di-print + SQLite).
    429/5xx = transient -> tunggu lalu ulangi; 4xx lain = permanen -> False.
    """
    token, chat = creds()
    if not token or not chat:
        return False
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                    "disable_web_page_preview": True}, timeout=TIMEOUT)
            if r.ok:
                return True
            if r.status_code == 429:
                wait = 2.0 * (attempt + 1)
                try:
                    wait = max(wait, float((r.json() or {}).get("parameters", {}).get("retry_after", wait)))
                except Exception:
                    pass
                import time as _t
                _t.sleep(min(wait, 30))
                continue
            if 500 <= r.status_code < 600:
                import time as _t
                _t.sleep(1.5 * (attempt + 1))
                continue
            return False
        except Exception as e:
            last = e
            import time as _t
            _t.sleep(1.5 * (attempt + 1))
    if last is not None:
        import logging as _lg
        _lg.getLogger(__name__).debug("telegram gagal: %s", str(last)[:160])
    return False
