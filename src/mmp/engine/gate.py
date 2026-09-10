"""Gate: PASS hanya jika lolos veto + skor >= threshold."""
from __future__ import annotations

def decide(vetoes: list[str], confidence: float, cfg: dict, permissive: bool = False) -> tuple[str, str, float]:
    threshold = cfg["signal"]["min_confidence"]
    if permissive:
        threshold = 65.0
    if vetoes:
        return "REJECT", "VETO: " + "; ".join(vetoes[:4]), threshold
    if confidence >= threshold:
        return "PASS", f"confidence {confidence} >= {threshold}", threshold
    return "REJECT", f"confidence {confidence} < {threshold}", threshold
