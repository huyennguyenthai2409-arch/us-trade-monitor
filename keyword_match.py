"""Shared word-boundary keyword matching. Plain substring matching (`kw in text`)
was found to produce real false positives against live Federal Register text --
short keywords like "EV" matched inside "review", "EAR" matched inside "hearing"/
"year", and "rice" matched inside "price" (ubiquitous in AD/CVD notices via
"export price"/"U.S. price"). Word-boundary regex fixes this for both
single-word and multi-word/hyphenated keywords."""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=None)
def _pattern(keyword: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")


def contains_keyword(text: str, keyword: str) -> bool:
    return _pattern(keyword.lower()).search(text) is not None


def any_keyword(text: str, keywords: list[str]) -> bool:
    return any(contains_keyword(text, kw) for kw in keywords)
