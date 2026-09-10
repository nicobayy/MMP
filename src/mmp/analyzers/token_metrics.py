"""Token metrics: momentum, volume, struktur.
Menolak yang sudah parabolic (telat) maupun yang dump parah.
"""
from __future__ import annotations

def analyze_token(pair: dict, cfg: dict) -> tuple[float, list[str], dict]:
    t = cfg["token_metrics"]
    pc = pair.get("priceChange") or {}
    h1 = float(pc.get("h1") or 0)
    h24 = float(pc.get("h24") or 0)
    vol = pair.get("volume") or {}
    vol_h1 = float(vol.get("h1") or 0)

    score = 70.0  # baseline netral
    notes: list[str] = []

    if h24 < t["min_price_change_h24_pct"]:
        score -= 30; notes.append(f"dump h24 {h24:.0f}%")
    elif h24 > t["max_price_change_h24_pct"]:
        score -= 30; notes.append(f"parabolic h24 +{h24:.0f}% (telat)")
    elif 0 < h24 < 200:
        score += 10; notes.append(f"momentum h24 sehat +{h24:.0f}%")
    if h1 < t["min_price_change_h1_pct"]:
        score -= 15; notes.append(f"h1 lemah {h1:.0f}%")
    if vol_h1 >= t["min_volume_h1_usd"]:
        score += 10; notes.append(f"vol h1 ${vol_h1:,.0f} aktif")
    else:
        score -= 10; notes.append(f"vol h1 kecil ${vol_h1:,.0f}")

    # Bonus txns imbalance (buy pressure)
    tx = (pair.get("txns") or {}).get("h24") or {}
    buys, sells = int(tx.get("buys") or 0), int(tx.get("sells") or 0)
    if buys + sells > 0:
        br = buys / (buys + sells)
        if br >= 0.55:
            score += 10; notes.append(f"buy pressure {br:.0%}")
        elif br < 0.45:
            score -= 10; notes.append(f"sell pressure {br:.0%}")

    meta = {"h1": h1, "h24": h24, "vol_h1": vol_h1, "buys_h24": buys, "sells_h24": sells}
    return float(max(0.0, min(100.0, score))), notes, meta
