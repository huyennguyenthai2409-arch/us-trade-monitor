"""Dashboard summary text (not part of the classification/scoring pipeline --
purely a display concern for app.py). Pulls a duty/tariff rate out of the
abstract when one is actually stated, and trims the abstract to a short,
direct lead sentence instead of a blind character slice.

Federal Register abstracts only state a specific rate for a minority of
documents (most AD/CVD notices defer the number to the full text/annex the
API doesn't expose -- see README's "Known limitation"), so `extract_rate`
returns None far more often than not. That's expected, not a bug: showing
nothing is correct when the source document itself doesn't state a number
here, per the workspace's "never fabricate a figure" rule.
"""

from __future__ import annotations

import re

# Only these legal-basis categories carry a duty/tariff-rate concept at all --
# gating on this avoids misreading an unrelated percentage (BIS export-control
# ownership thresholds, OFAC/IRS interest-rate notices, compliance quotas) as
# a tariff rate.
_RATE_BEARING_LEGAL_BASIS = {
    "AD_CVD", "SECTION_232", "SECTION_301", "SECTION_201", "SECTION_337", "IEEPA_PRESIDENTIAL",
}

_RATE_CONTEXT_WORDS = (
    "duty", "dumping", "countervailing", "margin", "tariff", "cash deposit", "bond", "ad valorem", "rate",
)
_RATE_EXCLUDE_WORDS = ("interest rate", "owned by", "comply", "allocate", "eliminate")

_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*percent\b\s*(?:to|-|–|through)\s*(\d+(?:\.\d+)?)\s*percent\b", re.I
)
_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*percent\b", re.I)

_CONTEXT_WINDOW = 80


def _has_context(text: str, start: int) -> bool:
    window = text[max(0, start - _CONTEXT_WINDOW):start].lower()
    if any(bad in window for bad in _RATE_EXCLUDE_WORDS):
        return False
    return any(good in window for good in _RATE_CONTEXT_WORDS)


def extract_rate(text: str, legal_basis: list[str]) -> str | None:
    """Returns a short 'X%' or 'X% to Y%' string if the text states a rate
    plausibly tied to a tariff/duty (per legal_basis + nearby context), else
    None -- never guesses or estimates."""
    if not any(b in _RATE_BEARING_LEGAL_BASIS for b in legal_basis):
        return None

    for m in _RANGE_RE.finditer(text):
        if _has_context(text, m.start()):
            return f"{m.group(1)}% to {m.group(2)}%"

    for m in _SINGLE_RE.finditer(text):
        if _has_context(text, m.start()):
            return f"{m.group(1)}%"

    return None


def short_summary(title: str, abstract: str, rate: str | None, max_chars: int = 260) -> str:
    """Short, direct summary: rate up front when we have one, then the
    abstract (falling back to the title) trimmed to max_chars at a word
    boundary. Deliberately not sentence-based -- these abstracts are full of
    abbreviations ("U.S.", "Ltd.", "Inc.") that break period-based sentence
    splitting."""
    body = abstract.strip() or title.strip()

    prefix = f"Rate: {rate}. " if rate else ""
    budget = max(0, max_chars - len(prefix))

    if len(body) <= budget:
        return f"{prefix}{body}"

    cut = body[:budget]
    last_space = cut.rfind(" ")
    if last_space > budget * 0.6:
        cut = cut[:last_space]
    return f"{prefix}{cut.rstrip('.,;: ')}…"
