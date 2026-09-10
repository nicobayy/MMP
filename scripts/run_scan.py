"""Entry point: python scripts/run_scan.py --help"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mmp.config import load_config, db_path
from mmp.collectors import dexscreener as dex
from mmp.collectors import universe as uni
from mmp.collectors import helius as hel
from mmp.collectors import birdeye as bir
from mmp.collectors import geckoterminal as gecko
from mmp.engine.signal import generate
from mmp.risk.position import build_plan
from mmp.storage.store import connect, save, should_alert, mark_alerted
from mmp.storage import wallets as wal
from mmp.storage import kol as koldb
from mmp.storage import paper as pstore
from mmp.notifiers.telegram import format_signal, format_summary, send_telegram

def enrichment_for_pair(pair: dict, cfg, use_helius: bool) -> dict:
    he = helius_for_pair(pair, cfg, use_helius)
    # Birdeye cross-check (Solana, bila key ada): holders count EVM-tak-ada.
    if (pair.get("chainId") or "") == "solana" and bir.has_key() \
            and (cfg.get("birdeye") or {}).get("enabled", True):
        try:
            mint = ((pair.get("baseToken") or {}).get("address")) or ""
            be = bir.build_enrichment(mint)
            for k, v in be.items():
                he.setdefault(k, v)
        except Exception:
            pass
    return he

def helius_for_pair(pair: dict, cfg, use_helius: bool) -> dict:
    if not use_helius or not hel.has_key():
        return {}
    if (pair.get("chainId") or "") != "solana":
        return {}  # Helius hanya Solana
    if not (cfg.get("helius") or {}).get("enabled", True):
        return {}
    mint = ((pair.get("baseToken") or {}).get("address")) or ""
    try:
        return hel.build_enrichment(mint, cfg)
    except Exception:
        return {}

def handle_pair(pair: dict, cfg, args, con) -> tuple[str, dict]:
    he = enrichment_for_pair(pair, cfg, args.use_helius)
    # KOL confluence nyata dari DB (bukan klaim): callout 48 jam terakhir.
    kol_callouts: list = []
    try:
        koldb.init(con)
        mint = ((pair.get("baseToken") or {}).get("address")) or ""
        kol_callouts = koldb.recent_for_token(con, mint, int((cfg.get("kol") or {}).get("window_hours", 48)))
    except Exception:
        kol_callouts = []
    # Tracker: hitung overlap trusted wallet (hemat: hanya dari holder_accounts yg sudah diambil)
    n_overlap = 0
    if (cfg.get("tracker") or {}).get("enabled", True):
        try:
            wal.init(con)
            t = wal.trusted(con, int(cfg["tracker"].get("min_trades", 5)), float(cfg["tracker"].get("min_win_rate", 0.6)))
            holders = he.get("holder_accounts", []) if he else []
            _, n_overlap = wal.overlap_bonus(holders, t) if (holders and t) else (0.0, 0)
        except Exception:
            n_overlap = 0
    sig = generate(pair, cfg, permissive=args.permissive, helius_enrich=he,
                   trusted_overlap=n_overlap, kol_callouts=kol_callouts or None)
    sig.plan = build_plan(sig.price_usd, cfg)
    row = save(con, sig)
    sig_dict = sig.to_dict()
    sig_dict["db_id"] = row
    # Simpan kandidat wallet bila PASS + Solana + alamat token valid
    # (pair Gecko fallback tak punya token address -> skip agar DB tak kotor).
    if sig.verdict == "PASS" and sig.token_address and he.get("holder_accounts") \
            and (cfg.get("tracker") or {}).get("enabled", True):
        try:
            for acct in he["holder_accounts"][:10]:
                wal.add_sighting(con, acct, sig.token_address, sig.symbol)
        except Exception:
            pass
    print("=" * 70)
    print(f"[{sig.verdict}] {sig.symbol} {sig.chain} conf={sig.confidence} (min {sig.threshold}) | db#{row}")
    print(f"  reason: {sig.reason}")
    if sig.vetoes:
        print(f"  vetoes: {sig.vetoes}")
    print(f"  scores: {sig.scores}")
    print(f"  price: ${sig.price_usd} | liq: {sig.meta.get('liquidity')} | mcap: {sig.meta.get('mcap')}")
    if he:
        print(f"  helius: top10={he.get('top10_pct')}% top1={he.get('top_holder_pct')}% mint_renounced={he.get('mint_renounced')} overlap={n_overlap}")
    elif args.use_helius and pair.get("chainId") == "solana":
        print("  helius: OFF (isi HELIUS_API_KEY di .env)")
    print(f"  plan: {sig.plan}")
    if args.notify and sig.verdict == "PASS":
        cd = int((cfg.get("telegram") or {}).get("cooldown_min", 120))
        if should_alert(con, sig.pair_address, cd):
            ok = send_telegram(format_signal(sig))
            if ok:
                mark_alerted(con, sig.pair_address)
            print(f"  telegram: {'sent' if ok else 'skip (isi .env dulu)'}")
        else:
            print(f"  telegram: skip (cooldown {cd}m, sudah Pernah dikirim)")
    # Paper auto-open tiap PASS (dedup: 1 pair max 1 OPEN; TIER-2 size setengah).
    if args.paper and sig.verdict == "PASS":
        try:
            pstore.init(con)
            if pstore.has_open(con, sig.pair_address):
                print("  paper: skip (sudah ada OPEN di pair ini)")
            else:
                rp = cfg.get("paper") or {}
                rt = cfg.get("tiers") or {}
                risk = float(rt.get("tier2_size_pct", 0.5)) if sig.tier == 2 else float(rp.get("risk_pct", 1.0))
                pid = pstore.open_from_signal(con, sig_dict, risk)
                print(f"  paper: opened #{pid} (TIER-{sig.tier}, risk {risk}%)")
        except Exception as e:
            print(f"  paper: skip ({e})")
    return sig.verdict, sig_dict

def main():
    ap = argparse.ArgumentParser(description="MMP scanner — multi-chain, Solana prioritas")
    ap.add_argument("--token", help="Alamat token")
    ap.add_argument("--chain", default="solana", help="chainId DexScreener (default solana, atau 'any')")
    ap.add_argument("--chains", default=None, help="Override multi-chain, mis. 'solana,base,bsc' (default ikut config)")
    ap.add_argument("--pair", help="Alamat pair + --chain untuk 1 pair spesifik")
    ap.add_argument("--top-boosts", action="store_true")
    ap.add_argument("--limit", type=int, default=10, help="Limit per chain (multi-chain)")
    ap.add_argument("--permissive", action="store_true")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--use-helius", action="store_true", default=True, help="Pakai Helius bila key ada (default on)")
    ap.add_argument("--no-helius", dest="use_helius", action="store_false")
    ap.add_argument("--paper", action="store_true", help="Buka posisi paper virtual tiap PASS")
    ap.add_argument("--gecko-fallback", action="store_true", default=True, help="Tambah universe EVM GeckoTerminal")
    ap.add_argument("--no-gecko-fallback", dest="gecko_fallback", action="store_false")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.chains:
        cfg["chains"]["enabled"] = [c.strip() for c in args.chains.split(",") if c.strip()]
    con = connect(db_path())
    n_pass = n_reject = 0

    if args.pair and args.chain:
        pair = dex.get_pair(args.chain, args.pair)
        if not pair:
            print("Pair tidak ditemukan."); return
        handle_pair(pair, cfg, args, con)
        return

    if args.token:
        pairs = dex.get_token_pairs(args.chain, args.token)
        if not pairs:
            print("Token tidak ditemukan di DexScreener."); return
        best = dex.pick_best_pair(pairs)
        print(f"Ditemukan {len(pairs)} pair, memakai yang paling likuid: {best.get('dexId')} {best.get('pairAddress')}")
        handle_pair(best, cfg, args, con)
        return

    if args.top_boosts:
        try:
            boosts = dex.get_top_boosts()
        except Exception as e:
            print(f"DexScreener boosts gagal ({e}). Coba fallback GeckoTerminal EVM...")
            boosts = []
        pairs = uni.universe_from_boosts(boosts, cfg, limit_per_chain=args.limit) if boosts else []
        if args.gecko_fallback:
            try:
                extra = gecko.universe_fallback(cfg, per_chain=3)
                seen = {p.get("pairAddress") for p in pairs}
                pairs += [p for p in extra if p.get("pairAddress") not in seen]
            except Exception:
                pass
        if not pairs:
            print("Universe kosong (semua sumber gagal). Coba lagi nanti.")
            return
        print(f"Scanning {len(pairs)} pairs chains={cfg['chains']['enabled']} (solana prioritas, permissive={args.permissive})...")
        if args.use_helius and not hel.has_key():
            print("NOTE: HELIUS_API_KEY kosong -> Helius off, auto-SM pakai DexScreener saja. Isi .env untuk akurasi Solana.")
        passes: list[dict] = []
        for best in pairs:
            try:
                v, d = handle_pair(best, cfg, args, con)
                n_pass += v == "PASS"; n_reject += v != "PASS"
                if v == "PASS":
                    passes.append(d)
            except Exception as e:
                print(f"- error {best.get('pairAddress')}: {e}"); n_reject += 1
        print(f"\nRingkasan: PASS={n_pass} REJECT={n_reject} (konservatif = REJECT banyak itu NORMAL)")
        if args.notify and (cfg.get("telegram") or {}).get("send_summary", True):
            ok = send_telegram(format_summary(n_pass, n_reject, passes))
            print(f"Summary telegram: {'sent' if ok else 'skip (isi .env dulu)'}")
        return

    ap.print_help()

if __name__ == "__main__":
    main()
