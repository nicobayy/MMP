"""Auto-discovery smart money TANPA list wallet manual.
Prinsip konservatif: skor auto max 85, butuh banyak konfluensi untuk >60.
Sumber: (1) Helius top holders bila ada, (2) struktur txns DexScreener.

Return: (score, notes, meta, wallets_proxy)
wallets_proxy: list kosong (tak ada wallet tracked) atau ringkasan distribusi.
"""
from __future__ import annotations


def discover(pair: dict, helius_enrich: dict | None = None, cfg: dict | None = None,
             trusted_overlap: int = 0, trusted_bonus: float | None = None,
             whale_buys_n: int = 0):
    cfg = cfg or {}
    sm_cfg: dict = cfg.get("smart_money_auto", {})
    max_score: float = float(sm_cfg.get("max_auto_score", 85))
    he = helius_enrich or {}

    tx = (pair.get("txns") or {}).get("h24") or {}
    buys, sells = int(tx.get("buys") or 0), int(tx.get("sells") or 0)
    total = buys + sells
    ratio = (buys / total) if total else 0.0
    liq = float(((pair.get("liquidity") or {}).get("usd")) or 0)
    vol = float(((pair.get("volume") or {}).get("h24")) or 0)
    vl = (vol / liq) if liq else 0.0

    score = 50.0
    notes: list[str] = ["auto-SM: tanpa list manual"]

    # 1. Buy ratio sehat (organik) vs botted/dump
    lo, hi = float(sm_cfg.get("healthy_buy_ratio_min", 0.50)), float(sm_cfg.get("healthy_buy_ratio_max", 0.70))
    if total >= 50 and lo <= ratio <= hi:
        score += 10
        notes.append(f"buy ratio organik {ratio:.0%}")
    elif total >= 50 and ratio > 0.80:
        score -= 10
        notes.append(f"buy ratio {ratio:.0%} terlalu miring (botted?)")
    elif total >= 50 and ratio < 0.45:
        score -= 10
        notes.append(f"sell pressure {ratio:.0%}")

    # 2. Aktivitas exit (proxy smart money masuk+keluar)
    if vl >= 2:
        score += 10
        notes.append(f"vol/liq {vl:.1f}x ramai")
    elif vl < 1:
        score -= 10
        notes.append(f"vol/liq {vl:.1f}x sepi")

    # 3. Distribusi holder dari Helius (bila ada)
    top10 = he.get("top10_pct")
    top1 = he.get("top_holder_pct")
    if top10 is not None:
        if float(top10) < 25:
            score += 15
            notes.append(f"top10 {top10}% tersebar")
        elif float(top10) > 40:
            score -= 15
            notes.append(f"top10 {top10}% pekat (bandar?)")
        else:
            score += 5
            notes.append(f"top10 {top10}% wajar")
    else:
        notes.append("tanpa data holder Helius (cap konservatif)")
    if top1 is not None and float(top1) > float(sm_cfg.get("max_top_holder_pct", 15.0)):
        score -= 20
        notes.append(f"top1 {top1}% dominan -> risiko dump")
    if he.get("mint_renounced") is True:
        score += 5
        notes.append("mint renounced +")
    elif he.get("mint_renounced") is False:
        score -= 10
        notes.append("mint masih aktif (mintable)")
    labels = [str(x).lower() for x in (he.get("labels") or [])]
    if "freezable-risk" in labels:
        score -= 10
        notes.append("freeze authority aktif (bisa bekukan holder)")

    # 4. Bonus wallet terpercaya (dari tracker DB, bukan klaim kosong).
    # trusted_bonus = jumlah confidence*5 per wallet overlap (proporsional);
    # bila None, pakai legacy flat 5 per overlap agar backward-compatible.
    if trusted_overlap > 0:
        bonus = min(float(trusted_bonus), 15.0) if trusted_bonus is not None \
            else min(trusted_overlap * 5.0, 15.0)
        score += bonus
        notes.append(f"{trusted_overlap}x trusted wallet overlap +{bonus:.1f}")

    # 5. Aktivitas whale real (whale_watch.py): wallet berbeda yang BUY token
    # ini dalam window jam terakhir. Kecil & dibatasi agar tak mendominasi.
    if whale_buys_n > 0:
        wbonus = min(float(whale_buys_n) * 3.0, 9.0)
        score += wbonus
        notes.append(f"{whale_buys_n} whale buy(s) window +{wbonus:.1f}")

    score = max(0.0, min(max_score, score))
    meta = {"auto_score": round(score, 2), "buy_ratio": round(ratio, 3),
            "vol_liq": round(vl, 2), "top10_pct": top10, "top1_pct": top1,
            "helius_used": bool(he), "wallets_tracked": 0, "trusted_overlap": trusted_overlap,
            "whale_buys": int(whale_buys_n)}
    return round(score, 2), notes, meta, []
