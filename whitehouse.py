"""White House presidential-actions scraper -- early-warning counterpart to
federal_register.py's PRESDOCU pull. An executive order / proclamation /
memorandum typically appears on whitehouse.gov the day it's signed, often
days before its formal Federal Register publication, so this catches trade
actions sooner than the FR-only pipeline could.

No public API (see web_scrape_common.py). The /presidential-actions/
listing is a standard WordPress Query Loop block -- verified live
2026-08-21: each entry is an <li class="wp-block-post ..."> with a
title link, category tags, and an ISO datetime, newest first, paginated at
/presidential-actions/page/N/."""

from __future__ import annotations

import datetime as dt

from bs4 import BeautifulSoup

from web_scrape_common import fetch_soup, meta_description

BASE_URL = "https://www.whitehouse.gov/presidential-actions"
MAX_PAGES = 20  # safety cap; newest-first pagination stops as soon as we pass start_date


def _parse_listing(soup: BeautifulSoup) -> list[dict]:
    items = []
    for li in soup.select("li.wp-block-post"):
        # No h2 constraint: WordPress's block editor lets a site set the
        # query-loop title to any heading level, and hardcoding h2 would
        # silently skip every item if this site ever uses h3 instead.
        link = li.select_one(".wp-block-post-title a")
        date_tag = li.select_one(".wp-block-post-date time[datetime]")
        if not link or not link.get("href") or not date_tag or not date_tag.get("datetime"):
            continue
        items.append({
            "url": link["href"].strip(),
            "title": link.get_text(strip=True),
            "publication_date": date_tag["datetime"][:10],
        })
    return items


def _normalize(item: dict, known: set[str]) -> dict:
    slug = item["url"].rstrip("/").rsplit("/", 1)[-1]
    document_id = f"WH-{slug}"
    abstract = ""
    if document_id not in known:
        try:
            abstract = meta_description(fetch_soup(item["url"]))
        except Exception:
            abstract = ""
    return {
        "document_id": document_id,
        "source": "White House - Presidential Actions",
        "source_url": item["url"],
        "source_agency": "The White House",
        "publication_date": item["publication_date"],
        "title": item["title"],
        "abstract": abstract,
        # Matches federal_register.py's own sentinel so classify.py's existing
        # "presidential document" fallback (-> "Presidential action") applies
        # here too when no more specific document_type keyword hits.
        "document_type": "Presidential Document",
        "case_number": "",
        "fr_citation": "",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def fetch_all(start_date: dt.date, end_date: dt.date, known_document_ids: set[str] | None = None) -> list[dict]:
    known = known_document_ids or set()
    out: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        url = f"{BASE_URL}/" if page == 1 else f"{BASE_URL}/page/{page}/"
        soup = fetch_soup(url)
        items = _parse_listing(soup)
        if not items:
            break

        # Don't stop at the first old item within a page: WordPress can pin
        # a "sticky" post to the top of every listing page regardless of its
        # publish date, which would otherwise look like "we've paged past
        # start_date" on page 1 and silently drop everything on page 2+.
        # Only stop once a whole page's oldest item is out of range.
        page_min_date = None
        for item in items:
            try:
                pub_date = dt.date.fromisoformat(item["publication_date"])
            except ValueError:
                continue
            if page_min_date is None or pub_date < page_min_date:
                page_min_date = pub_date
            if start_date <= pub_date <= end_date:
                out.append(_normalize(item, known))

        if page_min_date is not None and page_min_date < start_date:
            break
        page += 1

    return out
