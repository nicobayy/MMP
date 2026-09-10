"""Gate: PASS Tier-1 / Tier-2 / REJECT.
TIER-1 = keyakinan penuh (>=85). TIER-2 = otomatis-penuh-tanpa-KOL (75-84)
dengan syarat dual-source (dua sumber independen hadir DAN setuju:
Solana = Helius+Birdeye, EVM = DexScreener+honeypot.is).
Size setengah, paper-wajib. Veto tetap membunuh semua tier.
"""
from __future__ import annotations


def decide(vetoes: list[str], confidence: float, cfg: dict,
           permissive: bool = False, dual_source: bool = False) -> tuple[str, str, float, int]:
    t1 = float(cfg["signal"]["min_confidence"])
    tiers = cfg.get("tiers") or {}
    t2 = float(tiers.get("tier2_min", 75))
    if permissive:
        return "PASS", f"confidence {confidence} >= 65.0 (permissive)", 65.0, 1
    if vetoes:
        return "REJECT", "VETO: " + "; ".join(vetoes[:4]), t1, 0
    if confidence >= t1:
        return "PASS", f"confidence {confidence} >= {t1} (TIER-1)", t1, 1
    if confidence >= t2:
        if tiers.get("tier2_require_dual_source", True) and not dual_source:
            return "REJECT", (f"confidence {confidence} < {t1} "
                              "(syarat TIER-2 tak terpenuhi, lihat meta.dual)"), t1, 0
        return "PASS", (f"confidence {confidence} >= {t2} "
                        "(TIER-2: size 1/2, paper-wajib)"), t2, 2
    return "REJECT", f"confidence {confidence} < {t2}", t1, 0
