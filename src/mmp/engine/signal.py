"""Signal dataclass + generator (orkestrasi full funnel)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..analyzers import kol as kol_an
from ..analyzers import liquidity as liq_an
from ..analyzers import risk as risk_an
from ..analyzers import smart_money as sm_an
from ..analyzers import smart_money_auto as sma_an
from ..analyzers import token_metrics as tm_an
from . import gate as gt
from . import scoring as sc


@dataclass
class Signal:
    chain: str
    token_address: str
    symbol: str
    name: str
    price_usd: float
    pair_address: str
    dex: str
    confidence: float
    verdict: str  # PASS / REJECT
    reason: str
    threshold: float
    tier: int = 0  # 0=reject, 1=full size, 2=half size + paper-wajib
    vetoes: list[str] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)

    def to_dict(self): return asdict(self)

def _dual_check(pair: dict, enrichment: dict, cfg: dict) -> tuple[bool, str]:
    """Dual-source = dua sumber independen hadir DAN nilainya konsisten.
    Solana: Helius (mint/dist) + Birdeye (holders/mcap/liq).
    EVM: DexScreener + honeypot.is (tax diketahui, bukan honeypot).
    Konflik angka antar-sumber = data tak bisa dipercaya -> bukan dual.
    """
    tiers = cfg.get("tiers") or {}
    tol = float(tiers.get("dual_max_divergence", 3.0))
    en = enrichment or {}
    if (pair.get("chainId") or "") == "solana":
        if "mint_renounced" not in en:
            return False, "tanpa Helius"
        if en.get("holders") is None:
            return False, "tanpa Birdeye holders"
        try:
            checks = (("mcap", float(pair.get("marketCap") or 0), float(en.get("birdeye_mcap") or 0)),
                      ("liq", float(((pair.get("liquidity") or {}).get("usd")) or 0),
                       float(en.get("birdeye_liq") or 0)))
        except (TypeError, ValueError):
            return False, "angka tak valid"
        for name, a, b in checks:
            # Fail-closed: sisi pembanding yang hilang/nol = TAK BISA diverifikasi,
            # bukan "setuju". Jangan lewati diam-diam.
            if a <= 0 or b <= 0:
                return False, f"tak bisa verifikasi {name} (data timpang)"
            if max(a, b) / min(a, b) > tol:
                return False, f"konflik {name} {max(a, b) / min(a, b):.1f}x > {tol}x"
        return True, "Helius+Birdeye setuju"
    if not en.get("source_honeypot_is"):
        return False, "tanpa honeypot.is"
    if "honeypot" in [str(x).lower() for x in (en.get("labels") or [])]:
        return False, "honeypot"
    if tiers.get("tier2_evm_tax_required", True) and \
            (en.get("buy_tax") is None or en.get("sell_tax") is None):
        return False, "tax EVM tak diketahui"
    return True, "DexScreener+honeypot.is setuju"

def generate(pair: dict, cfg: dict, enrichment: dict | None = None,
             sm_wallets: list | None = None, kol_callouts: list | None = None,
             permissive: bool = False, helius_enrich: dict | None = None,
             trusted_overlap: int = 0, trusted_bonus: float | None = None,
             shilling_n: int = 0) -> Signal:
    enrichment = enrichment or {}
    # Gabung enrichment Helius (mint/top holders) ke enrichment risk.
    if helius_enrich:
        merged = dict(enrichment)
        for k, v in helius_enrich.items():
            merged.setdefault(k, v)
        enrichment = merged
    vetoes = risk_an.check_hard_veto(pair, cfg, enrichment)
    grade, grade_missing = risk_an.data_grade(pair, enrichment)
    if grade == "BLIND" and (cfg.get("risk") or {}).get("veto_on_blind", False):
        vetoes = vetoes + [f"DATA_BLIND: tanpa data keamanan ({', '.join(grade_missing)})"]

    liq_score, liq_notes, liq_meta = liq_an.analyze_exit(pair, cfg)
    safe_score, safe_notes = risk_an.risk_safety_score(pair, enrichment)
    tm_score, tm_notes, tm_meta = tm_an.analyze_token(pair, cfg)
    if sm_wallets:
        sm_score, sm_notes, sm_meta = sm_an.analyze_smart_money(pair, sm_wallets)
    elif (cfg.get("smart_money_auto") or {}).get("enabled", True):
        sm_score, sm_notes, sm_meta, _ = sma_an.discover(pair, helius_enrich, cfg, trusted_overlap, trusted_bonus)
    else:
        sm_score, sm_notes, sm_meta = sm_an.analyze_smart_money(pair, None)
    kol_score, kol_notes, kol_meta = kol_an.analyze_kol(pair, kol_callouts)
    kol_cfg = cfg.get("kol") or {}
    if shilling_n >= int(kol_cfg.get("shill_min_handles", 3)):
        kol_score = min(kol_score, float(kol_cfg.get("shill_cap", 30)))
        kol_notes.append(f"shilling? {shilling_n} handles/{kol_cfg.get('shill_window_hours', 6)}h -> cap {kol_cfg.get('shill_cap', 30)}")
        kol_meta["shilling_n"] = shilling_n

    scores = {"liquidity_exit": liq_score, "risk_safety": safe_score,
              "token_metrics": tm_score, "smart_money": sm_score, "kol": kol_score}
    if permissive:
        # Mode testing: jangan hukum keras karena data SM/KOL belum ada
        scores["smart_money"] = max(sm_score, 60.0)
        scores["kol"] = max(kol_score, 50.0)
        confidence = sc.weighted_score(scores, cfg["weights"])
        cap_notes: list[str] = ["permissive: SM/KOL disimulasikan netral"]
    else:
        confidence, cap_notes = sc.apply_conservative_rules(scores, cfg)

    dual_ok, dual_note = _dual_check(pair, enrichment, cfg)
    verdict, reason, threshold, tier = gt.decide(vetoes, confidence, cfg, permissive, dual_source=dual_ok)

    base = pair.get("baseToken") or {}
    price = float(pair.get("priceUsd") or 0)
    return Signal(
        chain=pair.get("chainId", "?"), token_address=base.get("address", "?"),
        symbol=base.get("symbol", "?"), name=base.get("name", "?"),
        price_usd=price, pair_address=pair.get("pairAddress", "?"),
        dex=pair.get("dexId", "?"), confidence=round(confidence, 2),
        verdict=verdict, reason=reason + (" | " + "; ".join(cap_notes) if cap_notes else ""),
        threshold=threshold, tier=tier, vetoes=vetoes, scores=scores,
        notes={"liquidity": liq_notes, "safety": safe_notes, "token": tm_notes,
               "sm": sm_notes, "kol": kol_notes},
        meta={"liquidity": liq_meta, "token": tm_meta, "sm": sm_meta, "kol": kol_meta,
              "mcap": pair.get("marketCap"), "fdv": pair.get("fdv"),
              "url": pair.get("url"),
              "dual": {"ok": dual_ok, "note": dual_note},
              "data_grade": risk_an.data_grade(pair, enrichment)[0]},
    )
