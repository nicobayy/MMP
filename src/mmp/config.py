"""Load config YAML + env override."""
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

def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path or os.getenv("MMP_CONFIG", str(DEFAULT_CONFIG)))
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg

def db_path() -> str:
    return os.getenv("MMP_DB", "data/mmp.db")
