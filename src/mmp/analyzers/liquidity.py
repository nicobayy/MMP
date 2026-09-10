"""Liquidity & Exit capability analyzer.
Pertanyaan inti: kalau kita masuk, bisa keluar dengan slippage wajar?

BATAS JUJUR model impact: order hipotetis TETAP $1000 vs likuiditas
(impact = 1000/liq*100). Bukan simulasi order book / AMM curve:
- meremehkan slippage untuk size >> $1k, melebihkan untuk size kecil;
- abaikan fee, MEV, dan likuiditas terkonsentrasi per tick (CLMM).
Pakai sebagai saringan kasar, bukan janji eksekusi.
"""
from __future__ import annotations


def analyze_exit(pair: dict, cfg: dict) -> tuple[float, list[str], dict]:
    liq_cfg = cfg["liquidity"]
    liq = float(((pair.get("liquidity") or {}).get("usd")) or 0)
    vol_h24 = float(((pair.get("volume") or {}).get("h24")) or 0)
    vol_h1 = float(((pair.get("volume") or {}).get("h1")) or 0)
    dex_id = pair.get("dexId", "?")
    chain = pair.get("chainId", "?")

    ratio = (vol_h24 / liq) if liq > 0 else 0.0
    # Estimasi price impact kasar untuk order ~$1000: impact ≈ 1000/liq * 100
    impact_1k = (1000 / liq * 100) if liq > 0 else 999.0

    score = 100.0
    notes: list[str] = []
    if liq < liq_cfg["min_liquidity_usd"]:
        score -= 50
        notes.append(f"liq rendah ${liq:,.0f}")
    elif liq < liq_cfg["min_liquidity_usd"] * 3:
        score -= 15
        notes.append(f"liq tipis ${liq:,.0f}")
    if ratio < liq_cfg["min_volume_to_liquidity_ratio"]:
        score -= 25
        notes.append(f"vol/liq rendah {ratio:.2f} (sepi, susah exit)")
    else:
        notes.append(f"vol/liq sehat {ratio:.2f}")
    impact_lim = float(liq_cfg.get("max_price_impact_1k_pct",
                                liq_cfg.get("max_price_impact_1sol_pct", 5.0)))
    if impact_1k > impact_lim:
        score -= 20
        notes.append(f"impact $1k {impact_1k:.1f}% (slippage besar)")
    if vol_h1 < 1000:
        score -= 10
        notes.append("vol h1 sangat kecil")
    notes.append(f"{dex_id} @ {chain}")

    meta = {"liquidity_usd": liq, "vol_h24": vol_h24, "vol_h1": vol_h1,
            "vol_liq_ratio": round(ratio, 3), "impact_1k_pct": round(impact_1k, 2)}
    return max(score, 0.0), notes, meta
