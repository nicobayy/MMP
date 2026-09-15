"""Momentum gate khusus sniper: bukti beli cepat, bukan tebakan.

Dipakai HANYA bila cfg punya section `momentum` dengan enabled: true
(filter tidak punya section ini -> perilakunya nol-berubah).
Tujuan: ganti "pasti bull" (mustahil) dengan bukti minimum yang bisa
dicek dalam hitungan detik dari field DexScreener yang sudah ada:
tekanan beli, akselerasi volume jam-terakhir, dan umur pair masih segar.
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


def momentum_gate(pair: dict, cfg: dict) -> tuple[bool, list[str]]:
    """Return (lolos, notes). Gagal = sinyal di-veto dengan alasan MOMENTUM."""
    m = cfg.get("momentum") or {}
    if not m.get("enabled", False):
        return True, []
    notes: list[str] = []
    try:
        min_h1 = float(m.get("min_h1_pct", 0.0))
        min_br = float(m.get("min_buy_ratio", 0.55))
        min_vol_h1 = float(m.get("min_vol_h1_usd", 2000))
        min_intensity = float(m.get("min_intensity", 1.5))
        max_age = float(m.get("max_age_minutes", 180))
        min_m5_br = float(m.get("min_m5_buy_ratio", 0.55))
        min_m5_txns = int(m.get("min_m5_txns", 5))
    except (TypeError, ValueError):
        return False, ["momentum: config tak numerik"]

    pc = pair.get("priceChange") or {}
    try:
        h1 = float(pc.get("h1") or 0)
    except (TypeError, ValueError):
        h1 = 0.0
    if h1 < min_h1:
        return False, [f"momentum: h1 {h1:.1f}% < {min_h1:.1f}% (lemah/dump)"]

    vol = pair.get("volume") or {}
    try:
        vol_h1 = float(vol.get("h1") or 0)
        vol_h24 = float(vol.get("h24") or 0)
    except (TypeError, ValueError):
        vol_h1, vol_h24 = 0.0, 0.0
    if vol_h1 < min_vol_h1:
        return False, [f"momentum: vol h1 ${vol_h1:,.0f} < ${min_vol_h1:,.0f} (sepi)"]
    if vol_h24 > 0:
        intensity = vol_h1 / (vol_h24 / 24)
        if intensity < min_intensity:
            return False, [f"momentum: intensitas {intensity:.1f}x < {min_intensity:.1f}x (tak berakselerasi)"]
        notes.append(f"intensitas vol {intensity:.1f}x")
    else:
        notes.append("vol h24 ~0 (pair sangat baru), lolos via vol h1")

    tx = (pair.get("txns") or {}).get("h24") or {}
    try:
        buys, sells = int(tx.get("buys") or 0), int(tx.get("sells") or 0)
    except (TypeError, ValueError):
        buys, sells = 0, 0
    # Bukti segar dulu: m5 adalah bucket terkecil DexScreener (verifikasi API).
    # Jendela parsial (< min_m5_txns) tak dianggap bukti -> fallback h24.
    m5 = (pair.get("txns") or {}).get("m5") or {}
    try:
        m5_buys, m5_sells = int(m5.get("buys") or 0), int(m5.get("sells") or 0)
    except (TypeError, ValueError):
        m5_buys, m5_sells = 0, 0
    if m5_buys + m5_sells >= min_m5_txns:
        m5_br = m5_buys / (m5_buys + m5_sells)
        if m5_br < min_m5_br:
            return False, [f"momentum: buy ratio m5 {m5_br:.0%} < {min_m5_br:.0%} (tekanan jual kini)"]
        notes.append(f"buy ratio m5 {m5_br:.0%} ({m5_buys + m5_sells} txn)")
    else:
        notes.append(f"m5 tipis ({m5_buys + m5_sells} txn), nilai via h24")
    if buys + sells > 0:
        br = buys / (buys + sells)
        if br < min_br:
            return False, [f"momentum: buy ratio {br:.0%} < {min_br:.0%} (tekanan jual)"]
        notes.append(f"buy ratio {br:.0%}")
    else:
        return False, ["momentum: tanpa data transaksi"]

    age = _pair_age_minutes(pair)
    if age is not None and age > max_age:
        return False, [f"momentum: umur {age:.0f}m > {max_age:.0f}m (bukan snipe segar)"]
    if age is not None:
        notes.append(f"umur {age:.0f}m")
    return True, notes
