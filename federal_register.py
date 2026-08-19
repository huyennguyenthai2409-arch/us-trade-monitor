"""Federal Register API connector (spec section 1 Tier A + section 19 no-miss matrix).

Federal Register (federalregister.gov) publishes formal actions from DOC/ITA,
USTR, USITC, BIS, OFAC, CBP, and the White House (as Presidential Documents),
so one connector against its public API covers most of Tier A instead of
building a separate scraper per agency. Slugs below were verified live
against https://www.federalregister.gov/api/v1/agencies.json.

No API key required.
"""

from __future__ import annotations

import datetime as dt
from typing import Iterable

import requests

BASE_URL = "https://www.federalregister.gov/api/v1"

# Verified agency slugs (spec section 1, Tier A #2-4, #6-8).
AGENCY_SLUGS = {
    "DOC_ITA": "international-trade-administration",
    "USTR": "trade-representative-office-of-united-states",
    "USITC": "international-trade-commission",
    "BIS": "industry-and-security-bureau",
    "OFAC": "foreign-assets-control-office",
    "CBP": "u-s-customs-and-border-protection",
}

# Presidential Documents (EOs, proclamations, memoranda -- spec section 1 Tier A #5)
# are not filed under a "White House" agency slug; they're their own FR `type`.
PRESIDENTIAL_TYPE = "PRESDOCU"

# Supplementary term-search sweep implementing spec section 19's "no-miss matrix"
# in condensed form -- catches direct/indirect Vietnam signals from agencies
# outside AGENCY_SLUGS (e.g. Congress, State) that the agency-filtered pull misses.
NO_MISS_TERMS = [
    "Vietnam antidumping",
    "Vietnam countervailing",
    "Vietnam safeguard",
    "Vietnam Section 232",
    "Vietnam Section 301",
    "Vietnam Section 337",
    "Vietnam forced labor",
    "Vietnam circumvention",
    "Vietnam transshipment",
    "Vietnam tariff",
    "China Vietnam circumvention",
    "China Vietnam transshipment",
    "China Vietnam substantial transformation",
]

REQUEST_TIMEOUT = 30
MAX_PAGES = 10  # safety cap; at 100/page that's 1000 docs per query, far above daily volume


def _paginate(url: str, params: dict) -> list[dict]:
    results: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        resp = requests.get(url, params={**params, "page": page}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        results.extend(payload.get("results", []))
        if not payload.get("next_page_url") or not payload.get("results"):
            break
        page += 1
    return results


DOCUMENT_FIELDS = [
    "document_number",
    "title",
    "abstract",
    "publication_date",
    "agencies",
    "type",
    "html_url",
    "docket_ids",
    "citation",
]


def fetch_agency_documents(start_date: dt.date, end_date: dt.date, agency_slugs: Iterable[str] | None = None) -> list[dict]:
    """Documents published by our Tier-A agency slugs in [start_date, end_date]."""
    slugs = list(agency_slugs) if agency_slugs is not None else list(AGENCY_SLUGS.values())
    params = {
        "conditions[agencies][]": slugs,
        "conditions[publication_date][gte]": start_date.isoformat(),
        "conditions[publication_date][lte]": end_date.isoformat(),
        "per_page": 100,
        "order": "newest",
        "fields[]": DOCUMENT_FIELDS,
    }
    raw = _paginate(f"{BASE_URL}/documents.json", params)
    return [_normalize_document(d, source="Federal Register") for d in raw]


def fetch_presidential_documents(start_date: dt.date, end_date: dt.date) -> list[dict]:
    """Executive Orders / Proclamations / Memoranda (spec section 1 Tier A #5)."""
    params = {
        "conditions[type][]": [PRESIDENTIAL_TYPE],
        "conditions[publication_date][gte]": start_date.isoformat(),
        "conditions[publication_date][lte]": end_date.isoformat(),
        "per_page": 100,
        "order": "newest",
        "fields[]": DOCUMENT_FIELDS,
    }
    raw = _paginate(f"{BASE_URL}/documents.json", params)
    return [_normalize_document(d, source="Federal Register - Presidential") for d in raw]


def fetch_public_inspection_current() -> list[dict]:
    """Documents on public inspection now -- appear 1-3 days before formal
    publication (spec section 1 Tier A #1 "Public Inspection"; early-warning value)."""
    resp = requests.get(f"{BASE_URL}/public-inspection-documents/current.json", timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    raw = resp.json().get("results", [])
    return [_normalize_public_inspection(d) for d in raw]


def search_term(term: str, start_date: dt.date, end_date: dt.date) -> list[dict]:
    """Full-text search sweep (spec section 19 no-miss matrix)."""
    params = {
        "conditions[term]": term,
        "conditions[publication_date][gte]": start_date.isoformat(),
        "conditions[publication_date][lte]": end_date.isoformat(),
        "per_page": 100,
        "order": "newest",
        "fields[]": DOCUMENT_FIELDS,
    }
    raw = _paginate(f"{BASE_URL}/documents.json", params)
    return [_normalize_document(d, source=f"Federal Register - term search ({term})") for d in raw]


def run_no_miss_sweep(start_date: dt.date, end_date: dt.date) -> list[dict]:
    out: list[dict] = []
    for term in NO_MISS_TERMS:
        out.extend(search_term(term, start_date, end_date))
    return out


def fetch_all(start_date: dt.date, end_date: dt.date) -> list[dict]:
    """Full daily pull: agency-filtered + presidential + no-miss term sweep +
    current public inspection. Caller (pipeline.py) is responsible for
    deduplicating by document_id across these overlapping sources."""
    out: list[dict] = []
    out.extend(fetch_agency_documents(start_date, end_date))
    out.extend(fetch_presidential_documents(start_date, end_date))
    out.extend(run_no_miss_sweep(start_date, end_date))
    out.extend(fetch_public_inspection_current())
    return out


def _agency_names(raw_agencies: list[dict]) -> str:
    return "; ".join(a.get("name", "") for a in raw_agencies if a.get("name"))


def _normalize_document(d: dict, source: str) -> dict:
    return {
        "document_id": d.get("document_number"),
        "source": source,
        "source_url": d.get("html_url"),
        "source_agency": _agency_names(d.get("agencies") or []),
        "publication_date": d.get("publication_date"),
        "title": d.get("title") or "",
        "abstract": d.get("abstract") or "",
        "document_type": d.get("type") or "",
        "case_number": "; ".join(d.get("docket_ids") or []),
        "fr_citation": d.get("citation") or "",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def _normalize_public_inspection(d: dict) -> dict:
    return {
        "document_id": d.get("document_number"),
        "source": "Federal Register - Public Inspection",
        "source_url": d.get("html_url"),
        "source_agency": "; ".join(d.get("agency_names") or []),
        "publication_date": d.get("publication_date") or d.get("filed_at", "")[:10],
        "title": d.get("title") or "",
        "abstract": d.get("excerpts") or "",
        "document_type": d.get("type") or "",
        "case_number": "; ".join(d.get("docket_numbers") or []),
        "fr_citation": "",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
