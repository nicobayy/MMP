"""Signal dataclass + generator (orkestrasi full funnel)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from ..analyzers import risk as risk_an
from ..analyzers import liquidity as liq_an
from ..analyzers import token_metrics as tm_an
from ..analyzers import smart_money as sm_an
from ..analyzers import smart_money_auto as sma_an
from ..analyzers import kol as kol_an
from . import scoring as sc
from . import gate as gt

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

def generate(pair: dict, cfg: dict, enrichment: dict | None = None,
             sm_wallets: list | None = None, kol_callouts: list | None = None,
             permissive: bool = False, helius_enrich: dict | None = None,
             trusted_overlap: int = 0) -> Signal:
    enrichment = enrichment or {}
    # Gabung enrichment Helius (mint/top holders) ke enrichment risk.
    if helius_enrich:
        merged = dict(enrichment)
        for k, v in helius_enrich.items():
            merged.setdefault(k, v)
        enrichment = merged
    vetoes = risk_an.check_hard_veto(pair, cfg, enrichment)

    liq_score, liq_notes, liq_meta = liq_an.analyze_exit(pair, cfg)
    safe_score, safe_notes = risk_an.risk_safety_score(pair, enrichment)
    tm_score, tm_notes, tm_meta = tm_an.analyze_token(pair, cfg)
    if sm_wallets:
        sm_score, sm_notes, sm_meta = sm_an.analyze_smart_money(pair, sm_wallets)
    elif (cfg.get("smart_money_auto") or {}).get("enabled", True):
        sm_score, sm_notes, sm_meta, _ = sma_an.discover(pair, helius_enrich, cfg, trusted_overlap)
    else:
        sm_score, sm_notes, sm_meta = sm_an.analyze_smart_money(pair, None)
    kol_score, kol_notes, kol_meta = kol_an.analyze_kol(pair, kol_callouts)

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

    verdict, reason, threshold, tier = gt.decide(
        vetoes, confidence, cfg, permissive,
        dual_source=("mint_renounced" in enrichment and enrichment.get("holders") is not None))

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
              "url": pair.get("url")},
    )
