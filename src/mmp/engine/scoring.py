"""Weighted scoring + conservative gate."""
from __future__ import annotations

def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    total_w = sum(weights.values())
    s = sum(scores.get(k, 0) * w for k, w in weights.items()) / max(total_w, 1)
    return round(s, 2)

def apply_conservative_rules(scores: dict[str, float], cfg: dict) -> tuple[float, list[str]]:
    """Terapkan aturan konservatif: SM auto di bawah min_score_to_count = dianggap kosong."""
    notes: list[str] = []
    base = weighted_score(scores, cfg["weights"])
    cap = 100.0
    sig = cfg["signal"]
    sm_min: float = float((cfg.get("smart_money_auto") or {}).get("min_score_to_count", 60))
    sm_empty = scores.get("smart_money", 0) <= 0 or scores.get("smart_money", 0) < sm_min
    if sig.get("require_smart_money") and sm_empty:
        cap = min(cap, 74.0)
        notes.append(f"capped 74: smart-money lemah ({scores.get('smart_money', 0)} < {sm_min})")
    if sig.get("require_kol_or_sm") and sm_empty and scores.get("kol", 0) == 0:
        cap = min(cap, 69.0)
        notes.append("capped 69: tanpa SM & KOL (spekulasi murni)")
    return min(base, cap), notes
