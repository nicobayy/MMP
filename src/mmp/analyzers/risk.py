"""Risk analyzer + HARD VETO.
Filosofi konservatif: satu veto fatal => REJECT langsung.
Data yang belum tersedia (holder, LP lock) TIDAK jadi veto,
tapi mengurangi skor via penalti agar tetap konservatif.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _pair_age_minutes(pair: dict) -> float | None:
    ts = pair.get("pairCreatedAt")
    if not ts:
        return None
    try:
        created = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
        return (datetime.now(timezone.utc) - created).total_seconds() / 60
    except Exception:
        return None

def check_hard_veto(pair: dict, cfg: dict, enrichment: dict | None = None) -> list[str]:
    """Return list alasan veto. Kosong = lolos veto."""
    r = cfg["risk"]
    reasons: list[str] = []
    enrichment = enrichment or {}

    liq = float(((pair.get("liquidity") or {}).get("usd")) or 0)
    vol_h24 = float(((pair.get("volume") or {}).get("h24")) or 0)
    txns_h24 = ((pair.get("txns") or {}).get("h24") or {})
    n_txns = int((txns_h24.get("buys") or 0) + (txns_h24.get("sells") or 0))

    if liq < r["min_liquidity_usd"]:
        reasons.append(f"LIQ_TOO_LOW: ${liq:,.0f} < ${r['min_liquidity_usd']:,}")
    if vol_h24 < r["min_volume_h24_usd"]:
        reasons.append(f"VOL_TOO_LOW: ${vol_h24:,.0f} < ${r['min_volume_h24_usd']:,}")
    if n_txns < r["min_txns_h24"]:
        reasons.append(f"TXNS_TOO_LOW: {n_txns} < {r['min_txns_h24']}")

    # Umur pair
    age = _pair_age_minutes(pair)
    if age is not None and age < r["min_pair_age_minutes"]:
        reasons.append(f"TOO_YOUNG: {age:.0f}min < {r['min_pair_age_minutes']}min")

    # FDV vs mcap
    try:
        fdv = float(pair.get("fdv") or 0)
        mcap = float(pair.get("marketCap") or 0)
        if fdv and mcap and (fdv / max(mcap, 1)) > r["max_fdv_to_mcap_ratio"]:
            reasons.append(f"FDV_MC_RATIO_HIGH: {fdv/max(mcap,1):.1f}x")
    except Exception:
        pass

    # Enrichment (bila sudah ada data premium)
    labels = [str(x).lower() for x in (enrichment.get("labels") or [])]
    for blocked in r.get("blocked_labels", []):
        if blocked.lower() in labels:
            reasons.append(f"BLOCKED_LABEL: {blocked}")

    for key, lim_key, name in [
        ("buy_tax", "max_buy_tax_pct", "BUY_TAX"),
        ("sell_tax", "max_sell_tax_pct", "SELL_TAX"),
    ]:
        if key in enrichment and enrichment[key] is not None:
            if float(enrichment[key]) > float(r[lim_key]):
                reasons.append(f"{name}_HIGH: {enrichment[key]}% > {r[lim_key]}%")

    if enrichment.get("holders") is not None:
        if int(enrichment["holders"]) < int(r["min_holders"]):
            reasons.append(f"HOLDERS_LOW: {enrichment['holders']} < {r['min_holders']}")
    if enrichment.get("top10_pct") is not None:
        if float(enrichment["top10_pct"]) > float(r["max_top10_holders_pct"]):
            reasons.append(f"CONCENTRATED: top10 {enrichment['top10_pct']}%")
    if enrichment.get("lp_lock_pct") is not None:
        if float(enrichment["lp_lock_pct"]) < float(r["min_lp_lock_pct"]):
            reasons.append(f"LP_UNLOCKED: {enrichment['lp_lock_pct']}% < {r['min_lp_lock_pct']}%")

    return reasons


def data_grade(pair: dict, enrichment: dict | None = None) -> tuple[str, list[str]]:
    """Mutu data keamanan: COMPLETE / PARTIAL / BLIND + field yang hilang.
    BLIND = tak ada sumber keamanan yang berkontribusi sama sekali.
    Bedakan 'berisiko' (skor rendah) dari 'buta' (tak ada data) agar audit jelas.
    """
    en = enrichment or {}
    chain = pair.get("chainId", "")
    missing: list[str] = []
    if chain == "solana":
        if "mint_renounced" not in en and "top10_pct" not in en and en.get("holders") is None:
            return "BLIND", ["helius", "birdeye"]
        if "mint_renounced" not in en:
            missing.append("mint/dist (helius)")
        if en.get("holders") is None:
            missing.append("holders (birdeye)")
    else:
        if not en.get("source_honeypot_is"):
            return "BLIND", ["honeypot.is"]
        if en.get("buy_tax") is None or en.get("sell_tax") is None:
            missing.append("tax")
    if not en:
        return "BLIND", ["semua sumber"]
    return ("COMPLETE", []) if not missing else ("PARTIAL", missing)


def risk_safety_score(pair: dict, enrichment: dict | None = None) -> tuple[float, list[str]]:
    """Skor 0-100 untuk keamanan. Penalti bila data penting belum ada."""
    enrichment = enrichment or {}
    score = 100.0
    notes: list[str] = []
    if enrichment.get("holders") is None:
        score -= 15
        notes.append("no holder data (-15)")
    if enrichment.get("lp_lock_pct") is None:
        score -= 15
        notes.append("no LP-lock data (-15)")
    if enrichment.get("buy_tax") is None:
        score -= 10
        notes.append("no tax data (-10)")
    labels = enrichment.get("labels") or []
    if labels:
        score -= 10
        notes.append(f"labels: {labels} (-10)")
    return max(score, 0.0), notes
