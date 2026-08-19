"""Risk scoring (spec section 10-11) and alert priority (spec section 12).
Rule-based only -- every sub-score is derived from flags already computed by
classify.py/exposure.py, nothing here is invented or estimated from outside data."""

from __future__ import annotations

# Spec section 11 stage -> score sub-table. STAGE_7 (review/modification of an
# existing order) and STAGE_8 (terminated) aren't in the spec's table; STAGE_7
# is treated as ongoing real impact (same weight as STAGE_6), STAGE_8 as
# resolved/no ongoing risk.
_STAGE_SCORE = {
    "STAGE_0": 2,
    "STAGE_1": 4,
    "STAGE_2": 7,
    "STAGE_3": 10,
    "STAGE_4": 12,
    "STAGE_5": 14,
    "STAGE_6": 15,
    "STAGE_7": 15,
    "STAGE_8": 0,
}

_HIGH_PROBABILITY_STAGES = {"STAGE_3", "STAGE_4", "STAGE_5", "STAGE_6", "STAGE_7"}
_MEDIUM_PROBABILITY_STAGES = {"STAGE_1", "STAGE_2"}


def stage_score(stage: str | None) -> int:
    if stage is None:
        return 3  # unknown stage: small nonzero default, not asserted certainty
    return _STAGE_SCORE.get(stage, 3)


def probability_score(stage: str | None) -> int:
    if stage in _HIGH_PROBABILITY_STAGES:
        return 10
    if stage in _MEDIUM_PROBABILITY_STAGES:
        return 5
    if stage == "STAGE_0":
        return 2
    return 0  # STAGE_8 (terminated) or unknown


def compute_risk_score(exposure: dict, stage: str | None, has_company_match: bool) -> int:
    """Spec section 10 formula: direct VN (0-30) + sector (0-20) + product/HS
    (0-20) + investigation stage (0-15) + tariff probability (0-10) + company (0-5)."""
    if exposure["vietnam_direct"]:
        direct_score = 30
    elif exposure["vietnam_indirect"]:
        direct_score = 15  # partial credit: indirect/circumvention signal, not a confirmed direct case
    else:
        direct_score = 0

    sector_score = 20 if exposure["sector_risk"] else 0

    if exposure["company_product_match"]:
        product_score = 20  # confirmed via companies.csv HS code overlap
    elif exposure["company_sector_match"]:
        product_score = 10  # sector-level match only, HS code not yet confirmed
    else:
        product_score = 0

    company_score = 5 if has_company_match else 0

    total = (
        direct_score
        + sector_score
        + product_score
        + stage_score(stage)
        + probability_score(stage)
        + company_score
    )
    return max(0, min(100, total))


def risk_level(score: int) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    if score >= 20:
        return "MONITOR"
    return "LOW"


def alert_level(exposure: dict, doc_type: str, legal_basis: list[str], stage: str | None, score: int) -> str:
    """Spec section 12 alert priority -- layers a few explicit "always
    CRITICAL/HIGH" overrides from the spec on top of the section 10 risk band,
    since a straight score threshold alone would under-alert some of the
    spec's named scenarios (e.g. a fresh Vietnam investigation initiation
    sitting at a MEDIUM score but that spec section 12 calls HIGH)."""
    base = risk_level(score)

    if exposure["vietnam_direct"]:
        if stage in {"STAGE_6", "STAGE_7"} and "AD_CVD" in legal_basis:
            return "CRITICAL"
        if doc_type == "Circumvention" and stage in {"STAGE_5", "STAGE_6"}:
            return "CRITICAL"
        if doc_type == "Exclusion / exemption" and exposure["company_sector_match"]:
            return "CRITICAL"
        if stage == "STAGE_2":
            return "HIGH" if base in {"LOW", "MONITOR"} else base
        if any(b in legal_basis for b in ("SECTION_301", "SECTION_232")):
            return "HIGH" if base in {"LOW", "MONITOR"} else base

    if "UFLPA_FORCED_LABOR" in legal_basis and exposure["company_sector_match"]:
        return "HIGH" if base in {"LOW", "MONITOR"} else base

    if exposure["third_country_risk"] and "AD_CVD" in legal_basis:
        return "MEDIUM" if base == "LOW" else base

    return base
