"""Vietnam exposure logic (spec section 9) + sector/company keyword matching
(spec section 4/5). Rule-based only -- flags are "possible match" signals for
analyst review, not confirmed exposure (spec section 20 false-positive control)."""

from __future__ import annotations

import pandas as pd

import config
from keyword_match import any_keyword, contains_keyword

_GLOBAL_PHRASES = ["all countries", "worldwide", "global", "non-market economy"]


def _text(document: dict) -> str:
    return f"{document.get('title', '')} {document.get('abstract', '')}".lower()


def match_countries(document: dict) -> dict:
    text = _text(document)
    c = config.countries()
    vietnam_terms = c["vietnam_terms"]
    china_terms = c["china_terms"]
    circumvention_terms = c["circumvention_terms"]
    other_watchlist = c["other_watchlist"]

    vietnam_named = any_keyword(text, vietnam_terms)
    china_named = any_keyword(text, china_terms)
    circumvention_signal = any_keyword(text, circumvention_terms)
    other_matched = [t for t in other_watchlist if contains_keyword(text, t)]

    return {
        "vietnam_named": vietnam_named,
        "china_named": china_named,
        "circumvention_signal": circumvention_signal,
        "other_countries": other_matched,
    }


def match_sectors(document: dict) -> list[str]:
    text = _text(document)
    matched = []
    for sector_name, keywords in config.sectors().items():
        if any_keyword(text, keywords):
            matched.append(sector_name)
    return matched


def match_companies(sectors_matched: list[str], companies_df: pd.DataFrame) -> pd.DataFrame:
    """Companies whose sector overlaps the event's matched sectors -- a
    possible match by sector only (spec section 5's HS-code mapping needs the
    user to fill in companies.csv; until then this is sector-level, not
    confirmed HS-code-level, exposure)."""
    if companies_df.empty or not sectors_matched:
        return companies_df.iloc[0:0]
    return companies_df[companies_df["sector"].isin(sectors_matched)]


def compute_exposure(document: dict, sectors_matched: list[str], matched_companies: pd.DataFrame) -> dict:
    countries = match_countries(document)

    vietnam_direct = countries["vietnam_named"]

    # Spec section 9: China/competitor + circumvention language is an
    # indirect-Vietnam / third-country signal on its own, even without an
    # explicit Vietnam mention (Vietnam is a common transshipment hub, so
    # this is deliberately a broad early-warning trigger).
    indirect_signal = countries["china_named"] and countries["circumvention_signal"]
    vietnam_indirect = indirect_signal
    third_country_risk = indirect_signal

    no_specific_country = not vietnam_direct and not countries["china_named"] and not countries["other_countries"]
    text = _text(document)
    global_measure = no_specific_country and any_keyword(text, _GLOBAL_PHRASES)

    sector_risk = bool(sectors_matched)

    has_hs_match = False
    if not matched_companies.empty and "hs_codes" in matched_companies.columns:
        has_hs_match = matched_companies["hs_codes"].fillna("").astype(str).str.strip().ne("").any()
    company_product_match = has_hs_match  # confirmed only when a company row has HS codes filled in
    company_sector_match = not matched_companies.empty  # possible match, sector-level only

    # All countries actually named in the text -- used both for display (the
    # dashboard's Country column) and as the relevance signal in pipeline.py
    # (a legal-basis keyword hit with no country/sector attached at all is
    # generic agency boilerplate, not a Vietnam-relevant event).
    countries_named = []
    if vietnam_direct:
        countries_named.append("Vietnam")
    if countries["china_named"]:
        countries_named.append("China")
    countries_named.extend(c.title() for c in countries["other_countries"])
    if not countries_named and global_measure:
        countries_named = ["Global / all countries"]

    return {
        "vietnam_direct": vietnam_direct,
        "vietnam_indirect": vietnam_indirect,
        "global_measure": global_measure,
        "third_country_risk": third_country_risk,
        "sector_risk": sector_risk,
        "company_product_match": company_product_match,
        "company_sector_match": company_sector_match,
        "other_countries": countries["other_countries"],
        "countries_named": countries_named,
    }
