"""Helius collector (Solana). Aktif hanya bila HELIUS_API_KEY ada.
Fokus hemat kredit: sedikit RPC call, semua failure -> {} (graceful).
Docs: https://docs.helius.dev/
"""
from __future__ import annotations
import os
import requests

TIMEOUT = 15

def api_key() -> str:
    return os.getenv("HELIUS_API_KEY", "").strip().strip('"').strip("'")

def has_key() -> bool:
    return bool(api_key())

def rpc_url() -> str:
    return f"https://mainnet.helius-rpc.com/?api-key={api_key()}"

def rpc(method: str, params: list, timeout: int = TIMEOUT):
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
    except Exception:
        return {}

def get_top_holders(mint: str, limit: int = 20) -> list[dict]:
    """Largest token accounts -> [{address, amount_ui}]. Gagal -> []."""
    try:
        res = rpc("getTokenLargestAccounts", [mint])
        vals = (res or {}).get("value", [])[:limit]
        return [{"address": v.get("address"), "amount_raw": float(v.get("amount", 0))} for v in vals]
    except Exception:
        return []

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
    except Exception:
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
                    seen.add(o); uniq.append(o)
            if uniq:
                out["holder_accounts"] = uniq
        if mi.get("mint_authority") is None:
            out["mint_renounced"] = True
        else:
            out["mint_renounced"] = False
            out.setdefault("labels", []).append("mintable-risk")
        # holders exact count butuh indexing berat -> jangan dipaksa, biarkan None
        # agar risk.py memberi penalti skor (konservatif) bukan veto.
    except Exception:
        pass
    return out
