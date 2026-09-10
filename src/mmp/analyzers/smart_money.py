"""Smart money interface.
MVP: belum ada API key => skor 0 + flag missing.
Nanti colok: Helius (Solana holder/transactions), Birdeye (trades),
atau DB wallet internal. Format enrichment standar sudah disiapkan
agar scoring tidak perlu diubah.
"""
from __future__ import annotations


def analyze_smart_money(pair: dict, wallets: list[dict] | None = None) -> tuple[float, list[str], dict]:
    """wallets: [{address, label, net_buy_usd, txs}] — bila None/empty => missing."""
    if not wallets:
        return 0.0, ["no smart-money data (colok Helius/Birdeye nanti)"], {"wallets_tracked": 0}
    buys = sum(1 for w in wallets if float(w.get("net_buy_usd", 0)) > 0)
    total = len(wallets)
    score = min(100.0, (buys / max(total, 1)) * 100)
    notes = [f"{buys}/{total} smart wallets net-buy"]
    return score, notes, {"wallets_tracked": total, "net_buyers": buys}
