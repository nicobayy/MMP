"""Entry point: python scripts/run_scan.py --help"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mmp import safety as guard
from mmp.collectors import birdeye as bir
from mmp.collectors import dexscreener as dex
from mmp.collectors import geckoterminal as gecko
from mmp.collectors import helius as hel
from mmp.collectors import honeypot_is as hp
from mmp.collectors import meter as _meter
from mmp.collectors import universe as uni
from mmp.config import db_path, load_config
from mmp.engine.signal import generate
from mmp.notifiers.telegram import format_signal, format_summary, send_telegram
from mmp.risk.position import build_plan
from mmp.storage import kol as koldb
from mmp.storage import paper as pstore
from mmp.storage import stats as stats_mod
from mmp.storage import wallets as wal
from mmp.storage.store import connect, mark_alerted, save, should_alert

log = logging.getLogger("mmp.run_scan")


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
        except Exception as e:
            log.debug("birdeye enrichment skip: %s", str(e)[:160])
    # honeypot.is (EVM, gratis): isi tax + flag honeypot yang selama ini kosong.
    elif (cfg.get("honeypot_is") or {}).get("enabled", True):
        try:
            ce = hp.build_enrichment(pair.get("chainId", ""),
                                     ((pair.get("baseToken") or {}).get("address")) or "")
            for k, v in ce.items():
                if k == "labels":
                    he.setdefault("labels", []).extend(x for x in v if x not in he.setdefault("labels", []))
                else:
                    he.setdefault(k, v)
        except Exception as e:
            log.debug("honeypot.is enrichment skip: %s", str(e)[:160])
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
    except Exception as e:
        log.debug("helius enrichment skip: %s", str(e)[:160])
        return {}

def handle_pair(pair: dict, cfg, args, con) -> tuple[str, dict, str]:
    """Return (verdict, sig_dict, hp_status). hp_status untuk instrumentasi
    cakupan: ok | no_tax | fail | na (lihat storage/stats.py)."""
    he = enrichment_for_pair(pair, cfg, args.use_helius)
    if (pair.get("chainId") or "") == "solana":
        hp_status = "na"
    elif not he.get("source_honeypot_is"):
        hp_status = "fail"
    elif he.get("buy_tax") is None or he.get("sell_tax") is None:
        hp_status = "no_tax"
    else:
        hp_status = "ok"
    # KOL confluence nyata dari DB: bobot reputasi per handle + cek shilling.
    kol_callouts: list = []
    shilling_n = 0
    try:
        koldb.init(con)
        mint = ((pair.get("baseToken") or {}).get("address")) or ""
        kol_cfg = cfg.get("kol") or {}
        kol_callouts = koldb.recent_for_token(con, mint, int(kol_cfg.get("window_hours", 48)))
        for c in kol_callouts:
            try:
                w, wlabel = koldb.handle_weight(con, c.get("handle", ""), c.get("trust", "trusted"))
                c["weight"] = w
                c["wlabel"] = wlabel
            except Exception:
                c["weight"] = 0.0
                c["wlabel"] = "unknown"
        shilling_n = koldb.recent_handles_count(con, mint, int(kol_cfg.get("shill_window_hours", 6)))
    except Exception as e:
        log.debug("kol lookup skip: %s", str(e)[:160])
        kol_callouts = []
        shilling_n = 0
    # Tracker: overlap trusted wallet dengan bobot confidence (proporsional).
    n_overlap = 0
    w_bonus: float | None = None
    if (cfg.get("tracker") or {}).get("enabled", True):
        try:
            wal.init(con)
            t = wal.trusted(con, int(cfg["tracker"].get("min_trades", 5)), float(cfg["tracker"].get("min_win_rate", 0.6)))
            holders = he.get("holder_accounts", []) if he else []
            if holders and t:
                weights = {w: wal.stats(con, w).get("confidence", 0.5) for w in t}
                b, n_overlap = wal.overlap_bonus(holders, t, weights=weights)
                w_bonus = b
        except Exception as e:
            log.debug("tracker overlap skip: %s", str(e)[:160])
            n_overlap = 0
            w_bonus = None
    # Whale feed: wallet RANKED berbeda yang BUY relevan (min SOL) belakangan.
    whale_buys_n = 0
    try:
        mint0 = ((pair.get("baseToken") or {}).get("address")) or ""
        if mint0 and (pair.get("chainId") or "") == "solana":
            tr_cfg = cfg.get("tracker") or {}
            whale_buys_n = wal.recent_whale_buys(
                con, mint0, int(tr_cfg.get("whale_window_h", 24)),
                trusted_only=True, min_trades=int(tr_cfg.get("min_trades", 5)),
                min_win_rate=float(tr_cfg.get("min_win_rate", 0.6)),
                min_sol=float(tr_cfg.get("whale_min_sol", 0.5)))
    except Exception as e:
        log.debug("whale buys lookup skip: %s", str(e)[:160])
    sig = generate(pair, cfg, permissive=args.permissive, helius_enrich=he,
                   trusted_overlap=n_overlap, trusted_bonus=w_bonus,
                   kol_callouts=kol_callouts or None, shilling_n=shilling_n,
                   whale_buys_n=whale_buys_n)
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
        except Exception as e:
            log.debug("wallet sighting skip: %s", str(e)[:160])
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
        ok_alert, why = guard.allow_new(con, cfg, sig.chain, for_alert=True)
        if not ok_alert:
            print(f"  telegram: skip (guard: {why})")
        elif should_alert(con, sig.pair_address, cd):
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
                return sig.verdict, sig_dict, hp_status
            ok_new, why = guard.allow_new(con, cfg, sig.chain)
            if not ok_new:
                print(f"  paper: skip (guard: {why})")
                return sig.verdict, sig_dict, hp_status
            rp = cfg.get("paper") or {}
            rt = cfg.get("tiers") or {}
            risk = float(rt.get("tier2_size_pct", 0.5)) if sig.tier == 2 else float(rp.get("risk_pct", 1.0))
            pid = pstore.open_from_signal(con, sig_dict, risk)
            print(f"  paper: opened #{pid} (TIER-{sig.tier}, risk {risk}%)")
        except Exception as e:
            print(f"  paper: skip ({e})")
    return sig.verdict, sig_dict, hp_status

def _process_pair(job: dict) -> tuple[str, dict | None, str, str, str]:
    """Proses 1 pair di worker thread: koneksi DB sendiri (SQLite tak boleh
    berbagi koneksi lintas thread), output ditangkap agar print tetap rapi.
    Return (verdict, sig_dict|None, hp_status, err, output)."""
    import contextlib
    import io
    cfg, args, pair = job["cfg"], job["args"], job["pair"]
    wcon = connect(db_path())
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            v, d, hp_status = handle_pair(pair, cfg, args, wcon)
        return v, d, hp_status, "", buf.getvalue()
    except Exception as e:
        return "ERROR", None, "fail", str(e)[:200], ""
    finally:
        try:
            wcon.close()
        except Exception:
            pass


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
    _meter.set_budgets(cfg.get("api_budgets"))
    from mmp.collectors import limits as _limits
    _limits.configure((cfg.get("concurrency") or {}).get("per_source"))
    if guard.is_killed():
        print("ABORT: KILL SWITCH aktif (data/STOP ada). Matikan via scripts/killswitch.py --off.")
        return
    if args.chains:
        cfg["chains"]["enabled"] = [c.strip() for c in args.chains.split(",") if c.strip()]
    con = connect(db_path())
    n_pass = n_reject = 0

    if args.pair and args.chain:
        from mmp import validators as _v
        if not _v.is_token_address(args.chain, args.pair):
            print(f"Alamat pair tak valid ({_v.explain(args.chain, args.pair)}).")
            return
        pair = dex.get_pair(args.chain, args.pair)
        if not pair:
            print("Pair tidak ditemukan.")
            return
        handle_pair(pair, cfg, args, con)
        return

    if args.token:
        from mmp import validators as _v
        if not _v.is_token_address(args.chain, args.token):
            print(f"Alamat token tak valid ({_v.explain(args.chain, args.token)}).")
            return
        pairs = dex.get_token_pairs(args.chain, args.token)
        if not pairs:
            print("Token tidak ditemukan di DexScreener.")
            return
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
        # Dedup pair (boosts bisa memuat token yang sama 2x -> jangan scan & catat ganda).
        uniq: list[dict] = []
        seen_addr: set[str] = set()
        for p in pairs:
            a = p.get("pairAddress")
            if a and a not in seen_addr:
                seen_addr.add(a)
                uniq.append(p)
        pairs = uniq
        print(f"Scanning {len(pairs)} pairs chains={cfg['chains']['enabled']} (solana prioritas, permissive={args.permissive})...")
        if args.use_helius and not hel.has_key():
            print("NOTE: HELIUS_API_KEY kosong -> Helius off, auto-SM pakai DexScreener saja. Isi .env untuk akurasi Solana.")
        workers = int((cfg.get("concurrency") or {}).get("scan_workers", 4))
        results: list[tuple[str, dict | None, str, str, str]] = []
        if workers > 1 and len(pairs) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as ex:
                results = list(ex.map(_process_pair, [dict(cfg=cfg, args=args, pair=p) for p in pairs]))
        else:
            results = [_process_pair(dict(cfg=cfg, args=args, pair=p)) for p in pairs]
        passes: list[dict] = []
        cov_items: list[dict] = []
        for v, d, hp_status, err, out in results:
            print(out, end="")
            if v == "ERROR":
                print(f"- error: {err}")
                n_reject += 1
                continue
            n_pass += v == "PASS"
            n_reject += v != "PASS"
            if v == "PASS" and d:
                passes.append(d)
            if d:
                cov_items.append({"grade": (d.get("meta") or {}).get("data_grade", "?"), "hp": hp_status})
        print(f"\nRingkasan: PASS={n_pass} REJECT={n_reject} (konservatif = REJECT banyak itu NORMAL)")
        print(_meter.line())
        cov = stats_mod.summarize_batch(cov_items)
        print(f"coverage: grade COMPLETE={cov['complete']} PARTIAL={cov['partial']} BLIND={cov['blind']}"
              f" | hp EVM ok={cov['hp_ok']} no_tax={cov['hp_no_tax']} fail={cov['hp_fail']}")
        try:
            stats_mod.save_batch(con, cov)
        except Exception as e:
            log.debug("simpan batch_stats skip: %s", str(e)[:160])
        if args.notify and (cfg.get("telegram") or {}).get("send_summary", True):
            ok = send_telegram(format_summary(n_pass, n_reject, passes))
            print(f"Summary telegram: {'sent' if ok else 'skip (isi .env dulu)'}")
        return

    ap.print_help()

if __name__ == "__main__":
    main()
