"""Risk scoring (spec section 10-11, adapted) and alert priority (spec
section 12, adapted). Rule-based only -- every sub-score is derived from
flags already computed by classify.py/exposure.py, nothing here is invented
or estimated from outside data.

Stage and risk-level vocabularies are simplified from the spec's original
9-stage / 5-band model to 4 stages and 3 risk tiers per user request."""

from __future__ import annotations

# Stage -> score sub-table (investigation-stage component of the 0-100 risk
# score, spec section 10-11's 0-15 range). "Điều tra" (review of an existing
# order) scores below "Sơ bộ"/"Cuối cùng" since, absent an explicit
# preliminary/final phrase also matching, it usually means a review just
# opened with no new determination yet.
_STAGE_SCORE = {
    "Khởi xướng": 5,
    "Điều tra": 8,
    "Sơ bộ": 11,
    "Cuối cùng": 15,
}

_HIGH_PROBABILITY_STAGES = {"Điều tra", "Sơ bộ", "Cuối cùng"}


def stage_score(stage: str | None) -> int:
    if stage is None:
        return 3  # unknown stage: small nonzero default, not asserted certainty
    return _STAGE_SCORE.get(stage, 3)


def probability_score(stage: str | None) -> int:
    if stage in _HIGH_PROBABILITY_STAGES:
        return 10
    if stage == "Khởi xướng":
        return 5
    return 0  # unknown stage


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
    """3-tier band (collapsed from spec section 10's 5-tier LOW/MONITOR/MEDIUM/
    HIGH/CRITICAL): Thấp 0-39, Trung bình 40-59, Cao 60-100."""
    if score >= 60:
        return "Cao"
    if score >= 40:
        return "Trung bình"
    return "Thấp"


def alert_level(exposure: dict, doc_type: str, legal_basis: list[str], stage: str | None, score: int) -> str:
    """Spec section 12 alert priority, adapted to the 3-tier scale -- layers a
    few explicit "bump to Cao" overrides on top of the risk band, since a
    straight score threshold alone would under-alert some of the spec's named
    scenarios (e.g. a fresh Vietnam investigation initiation sitting at
    Trung bình but that spec section 12 calls high-priority)."""
    base = risk_level(score)

    if exposure["vietnam_direct"]:
        if stage in {"Cuối cùng", "Điều tra"} and "AD_CVD" in legal_basis:
            return "Cao"
        if doc_type == "Circumvention" and stage == "Cuối cùng":
            return "Cao"
        if doc_type == "Exclusion / exemption" and exposure["company_sector_match"]:
            return "Cao"
        if stage == "Khởi xướng":
            return "Cao"
        if any(b in legal_basis for b in ("SECTION_301", "SECTION_232")):
            return "Cao"

    if "UFLPA_FORCED_LABOR" in legal_basis and exposure["company_sector_match"]:
        return "Cao"

    if exposure["third_country_risk"] and "AD_CVD" in legal_basis:
        return "Trung bình" if base == "Thấp" else base

    return base
