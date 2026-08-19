"""Deduplication (spec section 13). Never deletes a document row -- only
assigns a canonical_event_id so multiple filings under the same case (e.g.
initiation, preliminary, final, order all sharing a docket number) can be
browsed as one case thread later. Exact-duplicate document_ids (our own
connector's overlapping pull modes returning the same FR document) are
dropped at ingestion since they're the literal same record, not separate
source records to preserve."""

from __future__ import annotations

import difflib
import re

import pandas as pd

TITLE_SIMILARITY_THRESHOLD = 0.88


def drop_exact_duplicates(new_docs: list[dict]) -> list[dict]:
    """Drops exact-duplicate document_ids within the batch. Also drops any
    document with a missing document_id -- FR always sets this in practice,
    but a null id would otherwise round-trip through CSV as "" and look
    "new" again on every future run (None != "" in Python), re-ingesting the
    same document forever."""
    seen = set()
    out = []
    for d in new_docs:
        doc_id = d.get("document_id")
        if not doc_id:
            continue
        if doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(d)
    return out


def _normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def assign_canonical_event_id(document: dict, existing_events: pd.DataFrame) -> str:
    """existing_events: prior rows from events.csv (document_id, case_number,
    source_agency, title, canonical_event_id columns expected)."""
    case_number = (document.get("case_number") or "").strip()
    if case_number:
        # Same case number -> same case thread, regardless of which stage/filing this is.
        first_token = case_number.split(";")[0].strip()
        if first_token:
            return f"CASE::{first_token}"

    if existing_events is not None and not existing_events.empty:
        norm_title = _normalize_title(document.get("title", ""))
        same_agency = existing_events[existing_events["source_agency"] == document.get("source_agency", "")]
        for _, row in same_agency.iterrows():
            existing_norm = _normalize_title(str(row.get("title", "")))
            if not existing_norm:
                continue
            ratio = difflib.SequenceMatcher(None, norm_title, existing_norm).ratio()
            if ratio >= TITLE_SIMILARITY_THRESHOLD:
                return row["canonical_event_id"]

    return document["document_id"]
