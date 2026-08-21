"""USTR press-release scraper -- USTR announces Section 301/232 actions,
tariff changes, and trade-deal news via press release, often before (or
sometimes entirely instead of) a Federal Register filing, so the FR-only
pipeline misses or lags these.

No public API (see web_scrape_common.py). ustr.gov's press-releases index
(Drupal Views) renders its full history in one page load with no working
pager -- verified live 2026-08-21 (identical content with/without a
?page=N param) -- so this fetches it once and filters by date locally
instead of paginating. The same page also embeds an unrelated, undated
site-search block (state/country trade-data links) mixed in among the
`.views-row` divs; rows are only kept when they have both a real date and
a press-releases URL, which filters that noise out."""

from __future__ import annotations

import datetime as dt

from bs4 import BeautifulSoup

from web_scrape_common import fetch_soup, meta_description

LISTING_URL = "https://ustr.gov/about-us/policy-offices/press-office/press-releases"
PRESS_RELEASE_PATH = "/press-office/press-releases/"


def _parse_listing(soup: BeautifulSoup) -> list[dict]:
    rows = soup.select("div.views-row")
    items = []
    for row in rows:
        link = row.select_one(".views-field-title a")
        date_tag = row.select_one(".views-field-field-date time[datetime]")
        if not link or not link.get("href") or not date_tag or not date_tag.get("datetime"):
            continue
        href = link["href"]
        if PRESS_RELEASE_PATH not in href:
            continue
        url = href if href.startswith("http") else f"https://ustr.gov{href}"
        items.append({
            "url": url,
            "title": link.get_text(strip=True),
            "publication_date": date_tag["datetime"][:10],
        })
    if rows and not items:
        # Every .views-row was filtered out -- either a genuinely empty
        # listing (unlikely, USTR posts constantly) or the site changed its
        # URL convention/markup and PRESS_RELEASE_PATH no longer matches
        # anything. Either way this would otherwise look identical to
        # "USTR published nothing," so make it visible instead of silent.
        print(f"WARNING: ustr.py found {len(rows)} .views-row elements but 0 matched "
              f"PRESS_RELEASE_PATH={PRESS_RELEASE_PATH!r} -- site markup may have changed")
    return items


def _normalize(item: dict, known: set[str]) -> dict:
    slug = item["url"].rstrip("/").rsplit("/", 1)[-1]
    document_id = f"USTR-{slug}"
    abstract = ""
    if document_id not in known:
        try:
            abstract = meta_description(fetch_soup(item["url"]))
        except Exception:
            abstract = ""
    return {
        "document_id": document_id,
        "source": "USTR - Press Releases",
        "source_url": item["url"],
        "source_agency": "Office of the United States Trade Representative",
        "publication_date": item["publication_date"],
        "title": item["title"],
        "abstract": abstract,
        "document_type": "",
        "case_number": "",
        "fr_citation": "",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def fetch_all(start_date: dt.date, end_date: dt.date, known_document_ids: set[str] | None = None) -> list[dict]:
    known = known_document_ids or set()
    soup = fetch_soup(LISTING_URL)
    out = []
    for item in _parse_listing(soup):
        try:
            pub_date = dt.date.fromisoformat(item["publication_date"])
        except ValueError:
            continue
        if start_date <= pub_date <= end_date:
            out.append(_normalize(item, known))
    return out
