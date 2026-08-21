"""Commerce Department press releases via trade.gov (International Trade
Administration) -- commerce.gov itself sits behind a Cloudflare managed JS
challenge (confirmed live 2026-08-21: even /robots.txt returns a challenge
page, not a real response) and cannot be scraped with a plain HTTP client,
so ITA's own site -- the same agency already tracked via the DOC_ITA slug
in federal_register.py -- is the practical Commerce source for early
warning ahead of formal Federal Register publication.

No public API (see web_scrape_common.py). Unlike whitehouse.py/ustr.py,
trade.gov's /press-releases listing embeds its link list without per-row
publish dates (the only date elements on that page belong to an unrelated
block and don't line up with the press-release rows -- verified live, not
assumed), so this fetches each NEW item's own detail page for both the
date (schema.org JSON-LD `datePublished`) and the abstract. That per-item
fetch only happens for URLs not already in documents.csv, so daily runs
(a handful of new releases at most) stay cheap; MAX_NEW_DETAIL_FETCHES
just bounds the one-time first backfill."""

from __future__ import annotations

import datetime as dt
import json

from bs4 import BeautifulSoup

from web_scrape_common import fetch_soup, meta_description

LISTING_URL = "https://www.trade.gov/press-releases"
MAX_NEW_DETAIL_FETCHES = 150


def _parse_listing(soup: BeautifulSoup) -> list[dict]:
    # A single article can be linked more than once on this landing page
    # (a heading link, an image link, a "Read more" link all pointing at
    # the same URL) -- keep the LONGEST anchor text seen per URL rather
    # than the first, so a short "Read more"/"Learn more" link that happens
    # to precede the real heading link in DOM order can't clobber the title.
    best_title_by_url: dict[str, str] = {}
    order: list[str] = []
    for a in soup.select('a[href*="/press-release/"]'):
        href = a.get("href", "")
        if "/press-release/" not in href:
            continue
        url = href if href.startswith("http") else f"https://www.trade.gov{href}"
        if url.rstrip("/") == LISTING_URL.rstrip("/"):
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        if url not in best_title_by_url:
            order.append(url)
        if len(title) > len(best_title_by_url.get(url, "")):
            best_title_by_url[url] = title
    return [{"url": url, "title": best_title_by_url[url]} for url in order]


def _find_date_published(data):
    """Recursive search for a "datePublished" key anywhere in the parsed
    JSON-LD tree. trade.gov nests it under mainEntity.datePublished (a
    schema.org WebPage wrapping an Article), not at the top level or under
    @graph -- confirmed live 2026-08-21 -- and other pages on the same site
    could nest it differently again, so this walks the whole structure
    instead of assuming one fixed schema shape."""
    if isinstance(data, dict):
        value = data.get("datePublished")
        if isinstance(value, str) and value:
            return value
        for v in data.values():
            found = _find_date_published(v)
            if found:
                return found
    elif isinstance(data, list):
        for entry in data:
            found = _find_date_published(entry)
            if found:
                return found
    return None


def _detail_date(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.get_text() or "")
        except (TypeError, ValueError):
            continue
        date_published = _find_date_published(data)
        if date_published:
            return date_published[:10]
    return None


def fetch_all(start_date: dt.date, end_date: dt.date, known_document_ids: set[str] | None = None) -> list[dict]:
    known = known_document_ids or set()
    listing = _parse_listing(fetch_soup(LISTING_URL))

    out: list[dict] = []
    fetched = 0
    for index, item in enumerate(listing):
        slug = item["url"].rstrip("/").rsplit("/", 1)[-1]
        document_id = f"ITA-{slug}"
        if document_id in known:
            continue
        if fetched >= MAX_NEW_DETAIL_FETCHES:
            # Hitting this cap would otherwise look identical to "trade.gov
            # published nothing new" (fetch_all just returns fewer/no
            # results) -- surface it so a long gap since the last run (or a
            # first backfill) doesn't silently under-report.
            print(f"WARNING: commerce.py hit MAX_NEW_DETAIL_FETCHES={MAX_NEW_DETAIL_FETCHES}; "
                  f"{len(listing) - index} unprocessed listing item(s) skipped this run")
            break
        fetched += 1

        try:
            detail_soup = fetch_soup(item["url"])
            pub_date_str = _detail_date(detail_soup)
            if not pub_date_str:
                continue
            pub_date = dt.date.fromisoformat(pub_date_str)
        except Exception:
            continue
        if not (start_date <= pub_date <= end_date):
            continue

        out.append({
            "document_id": document_id,
            "source": "Commerce (ITA) - Press Releases",
            "source_url": item["url"],
            "source_agency": "International Trade Administration (Dept. of Commerce)",
            "publication_date": pub_date_str,
            "title": item["title"],
            "abstract": meta_description(detail_soup),
            "document_type": "",
            "case_number": "",
            "fr_citation": "",
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })

    return out
