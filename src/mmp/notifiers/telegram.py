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

def format_signal(s) -> str:
    d = s.to_dict() if hasattr(s, "to_dict") else s
    tier = int(d.get("tier", 1 if d.get("verdict") == "PASS" else 0))
    emoji = "✅" if d["verdict"] == "PASS" and tier == 1 else ("🔶" if d["verdict"] == "PASS" else "⛔")
    tier_txt = f"TIER-{tier}" + (" (size 1/2, paper-wajib)" if tier == 2 else "")
    sm = (d.get("meta") or {}).get("sm") or {}
    lines = [
        f"{emoji} <b>MMP {d['verdict']} {tier_txt}</b> | {_esc(d['symbol'])} ({_esc(d['chain'])})",
        f"Conf: <b>{d['confidence']}</b> (min {d['threshold']})",
        f"Harga: ${_esc(d['price_usd'])} | DEX: {_esc(d['dex'])}",
        f"MCap: {_esc((d.get('meta') or {}).get('mcap'))} | Liq: ${_esc(((d.get('meta') or {}).get('liquidity') or {}).get('liquidity_usd'))}",
        f"Data: {_esc((d.get('meta') or {}).get('data_grade', '?'))} | Dual: {_esc(((d.get('meta') or {}).get('dual') or {}).get('note', '-'))}",
        f"SM: {_esc(sm.get('auto_score', ''))} (overlap trusted: {_esc(sm.get('trusted_overlap', 0))})",
        f"Alasan: {_esc(d['reason'])}",
    ]
    if d.get("vetoes"):
        lines.append("Veto: " + "; ".join(_esc(v) for v in d["vetoes"][:4]))
    audit = format_checklist(d)
    if audit:
        lines.append(audit)
    lines.append("Skor: " + ", ".join(f"{_esc(k)}={float(v):.0f}" for k, v in (d.get("scores") or {}).items()))
    pl = (d.get("plan") or {})
    if pl:
        lines.append(f"Plan: Entry ${pl.get('entry')} | SL ${pl.get('stop_loss')} (-{pl.get('sl_pct')}%) | TP ${pl.get('take_profit')} (+{pl.get('tp_pct')}%) | RR {pl.get('RR')}")
    if (d.get("meta") or {}).get("url"):
        lines.append(f"<a href=\"{_esc(d['meta']['url'])}\">DexScreener</a>")
    lines.append("#MMP #MelokMelokProfit")
    return "\n".join(lines)

def format_summary(n_pass: int, n_reject: int, passes: list) -> str:
    t1 = sum(1 for p in passes if int(p.get("tier", 1)) == 1)
    t2 = sum(1 for p in passes if int(p.get("tier", 1)) == 2)
    lines = [f"📊 <b>MMP Summary</b> | PASS={n_pass} (T1={t1} T2={t2}) REJECT={n_reject}"]
    for p in passes[:10]:
        badge = f"T{int(p.get('tier', 1))}"
        lines.append(f"✅ [{badge}] {_esc(p['symbol'])} ({_esc(p['chain'])}) conf={p['confidence']} ${p['price_usd']}")
    if not passes:
        lines.append("Tidak ada PASS. Konservatif = normal.")
    return "\n".join(lines)

def creds() -> tuple[str, str]:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_telegram(text: str) -> bool:
    token, chat = creds()
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=TIMEOUT)
        return r.ok
    except Exception:
        return False
