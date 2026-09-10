"""KOL / callout confluence.
Reputasi dibayar track record, bukan popularitas:
- bobot per handle dari handle_weight() (proven 1.5 / baru 0.5 / downranked 0.0),
  DEDUP per handle (spam 10x oleh 1 akun = 1 suara) + effektif di-cap 3.0.
- tanpa data -> 0 (konservatif). Shilling massal MEMBATASI skor (cap param).
"""
from __future__ import annotations


def analyze_kol(pair: dict, callouts: list[dict] | None = None, cap: float = 100.0) -> tuple[float, list[str], dict]:
    if not callouts:
        return 0.0, ["no KOL callout data"], {"callouts": 0}
    best: dict[str, float] = {}
    for c in callouts:
        # L6: normalisasi handle — '@kanal' dan 'kanal' adalah akun yang sama.
        h = (c.get("handle") or "").strip().lstrip("@").lower() or "(anon)"
        if "weight" in c:
            w = float(c["weight"])
        else:
            w = 1.0 if c.get("trusted") else 0.0  # tak dikenal = nol (fail-closed)
        best[h] = max(best.get(h, 0.0), w)  # dedup: 1 handle = 1 suara terkuat
    eff = min(sum(best.values()), 3.0)
    score = min(100.0, 40 + eff * 20)
    notes = [f"{len(best)} handle unik eff={eff:.1f}"]
    if cap < 100:
        score = min(score, cap)
        notes.append(f"capped {cap:.0f}: shilling massal dicurigai")
    return score, notes, {"callouts": len(callouts), "handles": len(best), "trusted_eff": round(eff, 1)}
