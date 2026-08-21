"""Shared helpers for the HTML-scraping connectors (whitehouse.py, ustr.py,
commerce.py). Unlike federal_register.py, these sites have no public API --
verified 2026-08-21: whitehouse.gov's wp-json REST endpoints 403, ustr.gov
and trade.gov expose no jsonapi, and commerce.gov itself sits behind a
Cloudflare managed JS challenge that no plain HTTP client can pass (checked
via robots.txt, which normally never triggers a challenge)."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 30

# A generic modern-browser UA. whitehouse.gov's REST API blocks the default
# python-requests UA outright (403) even though the plain HTML pages behind
# it don't -- confirmed live, not a guess.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    # Parse raw bytes, not resp.text: when a server's Content-Type header
    # omits charset, requests falls back to Latin-1 per the HTTP spec even
    # though these pages are UTF-8 -- confirmed live (em dashes/curly quotes
    # came through as mojibake). BeautifulSoup sniffs the real encoding from
    # the bytes (meta charset tag / BOM) instead of trusting that header.
    return BeautifulSoup(resp.content, "html.parser")


def meta_description(soup: BeautifulSoup) -> str:
    """Best-effort one-paragraph abstract from a detail page's <meta
    description>/og:description -- these sites don't expose a body-text
    API, and fetching+cleaning the full article HTML is overkill when the
    meta description already gives classify.py/exposure.py real prose to
    keyword-match against (titles alone are often too generic)."""
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return ""
