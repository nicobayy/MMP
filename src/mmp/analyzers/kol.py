"""KOL / callout confluence interface.
MVP: skor 0 bila tidak ada data. Nanti: tracker channel Telegram/X.
"""
from __future__ import annotations

def analyze_kol(pair: dict, callouts: list[dict] | None = None) -> tuple[float, list[str], dict]:
    if not callouts:
        return 0.0, ["no KOL callout data"], {"callouts": 0}
    trusted = [c for c in callouts if c.get("trusted")]
    score = min(100.0, 40 + len(trusted) * 20)
    return score, [f"{len(trusted)} trusted KOL callouts"], {"callouts": len(callouts)}
