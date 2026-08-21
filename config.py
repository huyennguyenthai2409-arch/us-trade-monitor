"""Loads the editable YAML watchlists in config/. Edit the YAML files to
change keywords/sectors/countries -- no code changes needed."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent / "config"


@lru_cache
def legal_basis() -> dict:
    with open(CONFIG_DIR / "legal_basis.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def countries() -> dict:
    with open(CONFIG_DIR / "countries.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def sectors() -> dict:
    with open(CONFIG_DIR / "sectors.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def major_export_sectors() -> frozenset[str]:
    with open(CONFIG_DIR / "major_export_sectors.yaml", encoding="utf-8") as f:
        names = frozenset(yaml.safe_load(f) or [])
    unknown = names - sectors().keys()
    if unknown:
        raise ValueError(
            f"config/major_export_sectors.yaml lists sector(s) not defined in sectors.yaml: {sorted(unknown)} "
            "-- names must match a sectors.yaml key exactly (typo/case mismatch silently drops the sector otherwise)"
        )
    return names


def legal_basis_categories() -> dict:
    """Legal basis categories only (excludes the stage_phrases block)."""
    return {k: v for k, v in legal_basis().items() if k != "stage_phrases"}


def stage_phrases() -> dict:
    return legal_basis().get("stage_phrases", {})
