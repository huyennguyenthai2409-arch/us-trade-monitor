"""Daily pipeline orchestration (spec section 15): fetch -> normalize ->
dedupe -> classify -> extract -> score -> alert -> digest. CSV storage under
data/ (see plan rationale: git-friendly sync between the cloud scheduled
agent and the Streamlit dashboard, unlike a committed SQLite binary)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

import classify
import dedupe
import exposure
import federal_register
import scoring

DATA_DIR = Path(__file__).parent / "data"
DIGESTS_DIR = DATA_DIR / "digests"
STATE_PATH = DATA_DIR / "state.json"

DOCUMENTS_COLUMNS = [
    "document_id", "source", "source_url", "source_agency", "publication_date",
    "title", "abstract", "document_type", "case_number", "fr_citation", "fetched_at",
]

EVENTS_COLUMNS = [
    "event_id", "document_id", "canonical_event_id", "legal_basis", "document_type",
    "investigation_stage", "vietnam_direct", "vietnam_indirect", "global_measure",
    "third_country_risk", "sector_risk", "sectors_matched", "company_product_match",
    "company_sector_match", "other_countries", "low_confidence", "risk_score",
    "risk_level", "alert_level", "source_agency", "title", "publication_date",
    "source_url", "case_number", "fr_citation",
]

EVENT_COMPANY_COLUMNS = ["event_id", "company_id", "ticker", "sector", "match_type"]

ALERTS_COLUMNS = [
    "alert_id", "event_id", "alert_level", "generated_at", "headline",
    "publication_date", "source_url", "status",
]

DEFAULT_OVERLAP_DAYS = 3  # re-pull a small trailing window each run in case of late-published docs
DEFAULT_LOOKBACK_DAYS = 14  # first-ever run with no state.json


def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        return df[columns]
    return pd.DataFrame(columns=columns)


def _save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _fetch_window() -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    state = _load_state()
    last_run = state.get("last_run_date")
    if last_run:
        start = dt.date.fromisoformat(last_run) - dt.timedelta(days=DEFAULT_OVERLAP_DAYS)
    else:
        start = today - dt.timedelta(days=DEFAULT_LOOKBACK_DAYS)
    return start, today


def run_pipeline(start_date: dt.date | None = None, end_date: dt.date | None = None) -> dict:
    if start_date is None and end_date is None:
        start_date, end_date = _fetch_window()
    elif start_date is None or end_date is None:
        raise ValueError("start_date and end_date must both be provided, or both omitted")

    documents_df = _load_csv(DATA_DIR / "documents.csv", DOCUMENTS_COLUMNS)
    events_df = _load_csv(DATA_DIR / "events.csv", EVENTS_COLUMNS)
    event_company_df = _load_csv(DATA_DIR / "event_company.csv", EVENT_COMPANY_COLUMNS)
    alerts_df = _load_csv(DATA_DIR / "alerts.csv", ALERTS_COLUMNS)
    companies_df = _load_csv(
        DATA_DIR / "companies.csv",
        ["company_id", "ticker", "company_name", "sector", "subsector", "hs_codes", "us_exposure_notes"],
    )

    raw_docs = federal_register.fetch_all(start_date, end_date)
    raw_docs = dedupe.drop_exact_duplicates(raw_docs)

    known_document_ids = set(documents_df["document_id"])
    new_docs = [d for d in raw_docs if d["document_id"] not in known_document_ids]

    new_document_rows = []
    new_event_rows = []
    new_event_company_rows = []
    new_alert_rows = []

    for doc in new_docs:
        new_document_rows.append(doc)

        legal_basis = classify.classify_legal_basis(doc)
        doc_type = classify.classify_document_type(doc)
        stage = classify.classify_stage(doc)

        sectors_matched = exposure.match_sectors(doc)
        matched_companies = exposure.match_companies(sectors_matched, companies_df)
        exp = exposure.compute_exposure(doc, sectors_matched, matched_companies)

        is_core_agency_source = doc["source"] in (
            "Federal Register", "Federal Register - Presidential", "Federal Register - Public Inspection",
        )
        relevant = bool(
            legal_basis or exp["sector_risk"] or exp["vietnam_direct"] or exp["vietnam_indirect"]
            or exp["company_sector_match"] or is_core_agency_source
        )
        low_confidence = not relevant

        has_company_match = not matched_companies.empty
        score = scoring.compute_risk_score(exp, stage, has_company_match)
        r_level = scoring.risk_level(score)
        a_level = scoring.alert_level(exp, doc_type, legal_basis, stage, score)
        if low_confidence:
            score = min(score, 39)
            r_level = "Thấp"
            a_level = "Thấp"

        canonical_id = dedupe.assign_canonical_event_id(doc, events_df)

        event_id = f"EVT-{doc['document_id']}"
        event_row = {
            "event_id": event_id,
            "document_id": doc["document_id"],
            "canonical_event_id": canonical_id,
            "legal_basis": "; ".join(legal_basis),
            "document_type": doc_type,
            "investigation_stage": stage or "",
            "vietnam_direct": exp["vietnam_direct"],
            "vietnam_indirect": exp["vietnam_indirect"],
            "global_measure": exp["global_measure"],
            "third_country_risk": exp["third_country_risk"],
            "sector_risk": exp["sector_risk"],
            "sectors_matched": "; ".join(sectors_matched),
            "company_product_match": exp["company_product_match"],
            "company_sector_match": exp["company_sector_match"],
            "other_countries": "; ".join(exp["other_countries"]),
            "low_confidence": low_confidence,
            "risk_score": score,
            "risk_level": r_level,
            "alert_level": a_level,
            "source_agency": doc["source_agency"],
            "title": doc["title"],
            "publication_date": doc["publication_date"],
            "source_url": doc["source_url"],
            "case_number": doc["case_number"],
            "fr_citation": doc["fr_citation"],
        }
        new_event_rows.append(event_row)
        events_df = pd.concat([events_df, pd.DataFrame([event_row])], ignore_index=True)

        for _, company in matched_companies.iterrows():
            new_event_company_rows.append({
                "event_id": event_id,
                "company_id": company["company_id"],
                "ticker": company["ticker"],
                "sector": company["sector"],
                "match_type": "hs_code" if exp["company_product_match"] else "sector_keyword",
            })

        if a_level == "Cao":
            new_alert_rows.append({
                "alert_id": f"ALT-{event_id}",
                "event_id": event_id,
                "alert_level": a_level,
                "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "headline": f"[{doc['source_agency']}] {doc_type} — {doc['title'][:140]}",
                "publication_date": doc["publication_date"],
                "source_url": doc["source_url"],
                "status": "new",
            })

    if new_document_rows:
        documents_df = pd.concat([documents_df, pd.DataFrame(new_document_rows)], ignore_index=True)
    if new_event_company_rows:
        event_company_df = pd.concat([event_company_df, pd.DataFrame(new_event_company_rows)], ignore_index=True)
    if new_alert_rows:
        alerts_df = pd.concat([alerts_df, pd.DataFrame(new_alert_rows)], ignore_index=True)

    _save_csv(documents_df, DATA_DIR / "documents.csv")
    _save_csv(events_df, DATA_DIR / "events.csv")
    _save_csv(event_company_df, DATA_DIR / "event_company.csv")
    _save_csv(alerts_df, DATA_DIR / "alerts.csv")
    _save_state({"last_run_date": end_date.isoformat(), "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat()})

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "fetched": len(raw_docs),
        "new_documents": len(new_document_rows),
        "new_alerts": len(new_alert_rows),
        "new_events": [row for row in new_event_rows],
    }
