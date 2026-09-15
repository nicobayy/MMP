"""Eksperimen momentum sniper (paper-only): entry berbukti + exit cepat/trailing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mmp.analyzers.momentum import momentum_gate
from mmp.backtest.engine import CLOSED_STATUSES, simulate_trailing_exit, summarize
from mmp.config import load_config
from mmp.engine.signal import generate

CFG = {"momentum": {"enabled": True, "min_h1_pct": 0.0, "min_buy_ratio": 0.55,
                    "min_vol_h1_usd": 2000, "min_intensity": 1.5, "max_age_minutes": 180}}


def _pair(**kw):
    import time
    base = {"chainId": "solana", "dexId": "raydium", "pairAddress": "P",
            "pairCreatedAt": int(time.time() * 1000) - 10 * 60 * 1000,
            "baseToken": {"address": "M", "symbol": "T", "name": "T"},
            "priceUsd": "1.0", "liquidity": {"usd": 50000},
            "volume": {"h24": 48000, "h1": 5000},
            "txns": {"h24": {"buys": 120, "sells": 80}},
            "priceChange": {"h1": 4, "h24": 60},
            "marketCap": 500000, "fdv": 500000, "url": "https://x"}
    base.update(kw)
    return base


def _c(ts, o, h, low, c):
    return {"ts": ts, "o": o, "h": h, "l": low, "c": c, "v": 1.0}


def test_gate_pass_and_disabled():
    ok, notes = momentum_gate(_pair(), CFG)
    assert ok, notes
    ok2, _ = momentum_gate(_pair(priceChange={"h1": -5, "h24": 60}), CFG)
    assert ok2 is False, "h1 negatif = dumping, wajib veto"


def test_gate_rejects_weak_evidence():
    p = _pair(volume={"h24": 48000, "h1": 100})
    assert momentum_gate(p, CFG)[0] is False, "vol h1 tipis wajib veto"
    p = _pair(txns={"h24": {"buys": 30, "sells": 170}})
    assert momentum_gate(p, CFG)[0] is False, "tekanan jual wajib veto"
    p = _pair(volume={"h24": 240000, "h1": 2000})  # intensitas 0.2x
    assert momentum_gate(p, CFG)[0] is False, "tak berakselerasi wajib veto"
    p = _pair(txns={"h24": {"buys": 0, "sells": 0}})
    assert momentum_gate(p, CFG)[0] is False, "tanpa transaksi wajib veto"
    assert momentum_gate(_pair(), {})[0] is True, "tanpa section = filter tak berubah"


def test_gate_rejects_stale():
    import time
    p = _pair(pairCreatedAt=int(time.time() * 1000) - 300 * 60 * 1000)
    assert momentum_gate(p, CFG)[0] is False, "umur > max wajib veto (bukan snipe segar)"


def test_gate_m5_fresh_evidence():
    base_txns = {"h24": {"buys": 120, "sells": 80}, "m5": {"buys": 2, "sells": 18}}
    assert momentum_gate(_pair(txns=base_txns), CFG)[0] is False, "m5 jual-dominated wajib veto"
    thin = {"h24": {"buys": 120, "sells": 80}, "m5": {"buys": 1, "sells": 0}}
    assert momentum_gate(_pair(txns=thin), CFG)[0] is True, "m5 tipis -> fallback h24"
    strong = {"h24": {"buys": 120, "sells": 80}, "m5": {"buys": 15, "sells": 5}}
    ok, notes = momentum_gate(_pair(txns=strong), CFG)
    assert ok and any("m5" in n for n in notes), notes


def test_trailing_locks_profit():
    cs = [_c(0, 100, 102, 99, 101),      # +2%, belum aktivasi (8%)
          _c(3600, 101, 112, 100, 110),  # peak +12% -> trail 107.5
          _c(7200, 110, 111, 106, 107)]  # low 106 <= 107.5 -> TRAIL
    r = simulate_trailing_exit(0, 100.0, cs, 6.0, 15.0, 6.0, 8.0, 4.0)
    assert r["status"] == "TRAIL", r
    assert r["pnl_pct"] == 7.52, r  # trail 107.52, bukan TP/SL


def test_trailing_sl_first_and_tp_cap():
    cs = [_c(0, 100, 116, 90, 110)]  # sentuh SL+TP satu candle -> SL (konservatif)
    r = simulate_trailing_exit(0, 100.0, cs, 6.0, 15.0, 6.0, 8.0, 4.0)
    assert r["status"] == "SL", r
    cs = [_c(0, 100, 116, 99, 115)]  # TP +16% sebelum trailing sempat relevan
    r = simulate_trailing_exit(0, 100.0, cs, 6.0, 15.0, 6.0, 8.0, 4.0)
    assert (r["status"], r["pnl_pct"]) == ("TP", 15.0), r


def test_trailing_open_flat_and_timeout():
    cs = [_c(0, 100, 103, 99, 101), _c(3600, 101, 104, 100, 102)]
    r = simulate_trailing_exit(0, 100.0, cs, 6.0, 15.0, 6.0, 8.0, 4.0)
    assert r["status"] == "OPEN", r
    r = simulate_trailing_exit(0, 100.0, cs, 6.0, 15.0, 0.0, 8.0, 4.0)
    assert r["status"] == "TIMEOUT", r
    assert simulate_trailing_exit(0, 100.0, [], 6.0)["status"] == "NO_DATA"


def test_trail_counts_as_closed_win():
    rep = summarize([{"status": "TRAIL", "pnl_pct": 7.5},
                     {"status": "SL", "pnl_pct": -6.0}])
    assert rep["n"] == 2 and rep["trail"] == 1, rep
    assert "TRAIL" in CLOSED_STATUSES


def test_generate_vetoes_weak_momentum_only_when_enabled():
    cfg = dict(load_config("config/mmp_sniper.yaml"))
    cfg["risk"] = dict(cfg["risk"], min_liquidity_usd=1, min_volume_h24_usd=1,
                       min_txns_h24=1, min_holders=0, max_top10_holders_pct=100.0,
                       min_pair_age_minutes=0)
    weak = _pair(priceChange={"h1": -10, "h24": 60})
    s = generate(weak, cfg, helius_enrich={"mint_renounced": True})
    assert s.verdict == "REJECT" and any("MOMENTUM" in v for v in s.vetoes), (s.verdict, s.vetoes)


def test_sniper_yaml_experiment_flags():
    cfg = load_config("config/mmp_sniper.yaml")
    assert (cfg.get("momentum") or {}).get("enabled") is True
    assert (cfg.get("paper", {}).get("trailing") or {}).get("enabled") is True
