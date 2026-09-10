"""Helius collector (Solana). Aktif hanya bila HELIUS_API_KEY ada.
Fokus hemat kredit: sedikit RPC call, semua failure -> {} (graceful).
Docs: https://docs.helius.dev/
"""
from __future__ import annotations

import logging
import os

import requests

from . import limits as _limits
from . import meter as _meter

log = logging.getLogger(__name__)

TIMEOUT = 15


def _redact(msg: str) -> str:
    """M1: Helius memakai ?api-key= di URL (wajib oleh API-nya) — jangan
    biarkan key bocor ke log/stdout via str(exception) yang memuat URL."""
    import re
    return re.sub(r"(api-key=)[^&\s'\"]+", r"\1***", msg or "")

def api_key() -> str:
    return os.getenv("HELIUS_API_KEY", "").strip().strip('"').strip("'")

def has_key() -> bool:
    return bool(api_key())

def rpc_url() -> str:
    return f"https://mainnet.helius-rpc.com/?api-key={api_key()}"

def rpc(method: str, params: list, timeout: int = TIMEOUT):
    if not _meter.allow("helius"):
        raise RuntimeError("budget helius habis (circuit breaker)")
    with _limits.guard("helius"):
        _meter.count("helius")
        r = requests.post(rpc_url(), json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if "error" in j and j["error"]:
        raise RuntimeError(str(j["error"])[:300])
    return j.get("result")

def get_mint_info(mint: str) -> dict:
    """Return {supply, mint_authority, freeze_authority} atau {} bila gagal."""
    try:
        supply_res = rpc("getTokenSupply", [mint])
        supply = float((supply_res or {}).get("value", {}).get("amount", 0))
        decimals = int((supply_res or {}).get("value", {}).get("decimals", 9))
        info = rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        parsed = ((info or {}).get("value", {}) or {}).get("data", {}).get("parsed", {}).get("info", {})
        return {
            "supply_raw": supply,
            "decimals": decimals,
            "supply_ui": supply / (10 ** decimals) if decimals else supply,
            "mint_authority": parsed.get("mintAuthority"),
            "freeze_authority": parsed.get("freezeAuthority"),
        }
    except Exception as e:
        log.warning("helius get_mint_info gagal: %s", _redact(str(e))[:160])
        return {}

def get_top_holders(mint: str, limit: int = 20) -> list[dict]:
    """Largest token accounts -> [{address, amount_ui}]. Gagal -> []."""
    try:
        res = rpc("getTokenLargestAccounts", [mint])
        vals = (res or {}).get("value", [])[:limit]
        return [{"address": v.get("address"), "amount_raw": float(v.get("amount", 0))} for v in vals]
    except Exception as e:
        log.warning("helius get_top_holders gagal: %s", _redact(str(e))[:160])
        return []

def get_signatures(address: str, limit: int = 20) -> list[str]:
    """Signature transaksi terakhir sebuah wallet. Gagal -> []."""
    try:
        res = rpc("getSignaturesForAddress", [address, {"limit": max(1, min(int(limit), 100))}])
        return [s.get("signature", "") for s in (res or []) if s.get("signature")]
    except Exception as e:
        log.warning("helius get_signatures gagal: %s", _redact(str(e))[:160])
        return []

def parse_enhanced(signatures: list[str]) -> list[dict]:
    """Parse batch signature via Helius Enhanced Transactions API.
    Return list mentah apa adanya. Tanpa key / gagal -> []."""
    if not has_key() or not signatures:
        return []
    if not _meter.allow("helius"):
        return []
    try:
        with _limits.guard("helius"):
            _meter.count("helius")
            r = requests.post(f"https://api.helius.xyz/v0/transactions/?api-key={api_key()}",
                              json={"transactions": signatures[:100]}, timeout=TIMEOUT)
        r.raise_for_status()
        out = r.json()
        return out if isinstance(out, list) else []
    except Exception as e:
        log.warning("helius enhanced parse gagal: %s", _redact(str(e))[:160])
        return []

SOL_MINT = "So11111111111111111111111111111111111111112"

def wallet_token_flows(wallet: str, txns: list[dict]) -> list[dict]:
    """Ekstrak arus token untuk 1 wallet dari enhanced txns.
    Return [{mint, side: BUY|SELL, amount, signature, ts}].
    BUY = wallet MENERIMA token non-SOL (bayar pakai SOL/lain).
    Heuristik eksplisit: bukan akuntansi penuh (ignore fee/arb multi-hop).
    """
    flows = []
    for t in txns or []:
        sig = t.get("transaction", {}).get("signatures", [None])[0] or t.get("signature", "")
        ts = t.get("timestamp")
        try:
            sol_out = sum(float(n.get("amount") or 0)
                          for n in (t.get("nativeTransfers") or [])
                          if n.get("fromUserAccount") == wallet) / 1e9
        except (TypeError, ValueError):
            sol_out = 0.0
        for tr in t.get("tokenTransfers") or []:
            mint = tr.get("mint", "")
            if not mint or mint == SOL_MINT:
                continue
            to_u, from_u = tr.get("toUserAccount", ""), tr.get("fromUserAccount", "")
            try:
                amt = float(tr.get("tokenAmount") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            if to_u == wallet and from_u != wallet:
                flows.append({"mint": mint, "side": "BUY", "amount": amt,
                              "sol_spent": round(sol_out, 4), "signature": sig, "ts": ts})
            elif from_u == wallet and to_u != wallet:
                flows.append({"side": "SELL", "mint": mint, "amount": amt,
                              "sol_spent": 0.0, "signature": sig, "ts": ts})
    return flows

def get_accounts_owners(addresses: list[str]) -> dict[str, str]:
    """Resolve owner wallet tiap token account via 1 call getMultipleAccounts.
    Return {account_address: owner_wallet}. Gagal -> {} (fail-closed:
    lebih baik tanpa bonus overlap daripada cocokkan alamat yang salah).
    """
    addresses = [a for a in addresses if a]
    if not addresses:
        return {}
    try:
        res = rpc("getMultipleAccounts", [addresses, {"encoding": "jsonParsed"}])
        vals = (res or {}).get("value", [])
    except Exception as e:
        log.warning("helius getMultipleAccounts gagal: %s", _redact(str(e))[:160])
        return {}
    out: dict[str, str] = {}
    for addr, info in zip(addresses, vals):
        try:
            owner = ((info or {}).get("data", {}).get("parsed", {}).get("info", {}) or {}).get("owner")
            if owner:
                out[addr] = owner
        except Exception:
            continue
    return out

def build_enrichment(mint: str, cfg: dict | None = None) -> dict:
    """Enrichment standar untuk risk.py: holders, top10_pct, lp_lock_pct, labels, mint flags.
    holder_accounts berisi OWNER wallet (bukan alamat akun token) agar
    perbandingan antar-token valid. RPC gagal total -> {} (jangan karang data).
    """
    if not has_key() or not mint:
        return {}
    out: dict = {}
    try:
        mi = get_mint_info(mint)
        if not mi:
            return {}  # buta data -> jujur kosong, bukan mint_renounced palsu
        tops = get_top_holders(mint)
        supply = float(mi.get("supply_raw") or 0)
        if supply > 0 and tops:
            amts = sorted([float(t.get("amount_raw") or 0) for t in tops], reverse=True)
            top10 = sum(amts[:10]) / supply * 100
            out["top10_pct"] = round(top10, 2)
            out["top_holder_pct"] = round(amts[0] / supply * 100, 2) if amts else None
            owners = get_accounts_owners([t.get("address", "") for t in tops[:10]])
            seen: set[str] = set()
            uniq: list[str] = []
            for t in tops[:10]:
                o = owners.get(t.get("address", ""))
                if o and o not in seen:
                    seen.add(o)
                    uniq.append(o)
            if uniq:
                out["holder_accounts"] = uniq
        if mi.get("mint_authority") is None:
            out["mint_renounced"] = True
        else:
            out["mint_renounced"] = False
            out.setdefault("labels", []).append("mintable-risk")
        # Freeze authority aktif = red flag setara mint authority:
        # pemilik bisa membekukan akun holder kapan saja (rug-pull vector).
        if mi.get("freeze_authority") is not None:
            out.setdefault("labels", []).append("freezable-risk")
        # holders exact count butuh indexing berat -> jangan dipaksa, biarkan None
        # agar risk.py memberi penalti skor (konservatif) bukan veto.
    except Exception:
        pass
    return out
