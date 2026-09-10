"""KOL / callout confluence.
Skor dari callout 48 jam terakhir; callout dari handle TERBUKTI (proven:
win-rate >=60% dari >=3 outcome) berbobot 1.5x. Tanpa data -> 0 (konservatif).
Shilling terkoordinasi (banyak handle dalam window pendek) MEMBATASI skor,
bukan menambahnya — hype massal serentak = distribusi, bukan akumulasi.
"""
from __future__ import annotations


def analyze_kol(pair: dict, callouts: list[dict] | None = None, cap: float = 100.0) -> tuple[float, list[str], dict]:
    if not callouts:
        return 0.0, ["no KOL callout data"], {"callouts": 0}
    trusted = [c for c in callouts if c.get("trusted")]
    eff = sum(1.5 if c.get("proven") else 1.0 for c in trusted)
    score = min(100.0, 40 + eff * 20)
    notes = [f"{len(trusted)} trusted KOL callouts"
             + (f" ({sum(1 for c in trusted if c.get('proven'))} proven)" if trusted else "")]
    if cap < 100:
        score = min(score, cap)
        notes.append(f"capped {cap:.0f}: shilling massal dicurigai")
    return score, notes, {"callouts": len(callouts), "trusted_eff": round(eff, 1)}
