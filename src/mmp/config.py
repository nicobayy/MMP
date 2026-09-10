"""Load config YAML + env override + validasi skema (H3 fail-fast).

Tanpa validasi, salah hapus key / weights != 100 = KeyError di tengah
scan atau skor miring diam-diam. Di sini: gagal cepat dengan pesan jelas
SEBELUM scan membakar API call.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=getattr(logging, os.getenv("MMP_LOG", "WARNING").upper(), logging.WARNING),
                    format="%(levelname)s %(name)s: %(message)s")

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "mmp_config.yaml"

REQUIRED_TOP = ("signal", "tiers", "weights", "risk", "liquidity",
                "token_metrics", "position", "chains")
WEIGHT_KEYS = ("liquidity_exit", "risk_safety", "token_metrics",
               "smart_money", "kol")


def validate_config(cfg: dict) -> dict:
    """Validasi struktur + rentang wajar. Raise ValueError bila fatal."""
    if not isinstance(cfg, dict):
        raise ValueError("config bukan mapping YAML")
    missing = [k for k in REQUIRED_TOP if k not in cfg or cfg[k] is None]
    if missing:
        raise ValueError(f"config kurang section: {', '.join(missing)}")
    w = cfg.get("weights") or {}
    missing_w = [k for k in WEIGHT_KEYS if k not in w]
    if missing_w:
        raise ValueError(f"weights kurang: {', '.join(missing_w)}")
    try:
        total = sum(float(w[k]) for k in WEIGHT_KEYS)
    except (TypeError, ValueError) as e:
        raise ValueError(f"weights tak numerik: {e}") from e
    if abs(total - 100.0) > 1e-6:
        raise ValueError(f"weights total harus 100, dapat {total}")
    sig = cfg.get("signal") or {}
    for k in ("min_confidence", "permissive_confidence"):
        try:
            v = float(sig.get(k, 85 if k == "min_confidence" else 65))
        except (TypeError, ValueError) as e:
            raise ValueError(f"signal.{k} tak numerik: {e}") from e
        if not 0 <= v <= 100:
            raise ValueError(f"signal.{k} harus 0-100, dapat {v}")
    t1 = float(sig.get("min_confidence", 85))
    t2 = float((cfg.get("tiers") or {}).get("tier2_min", 75))
    if not t2 < t1:
        raise ValueError(f"tiers.tier2_min ({t2}) harus < signal.min_confidence ({t1})")
    return cfg


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path or os.getenv("MMP_CONFIG") or str(DEFAULT_CONFIG))
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return validate_config(cfg)

def db_path() -> str:
    return os.getenv("MMP_DB", "data/mmp.db")
