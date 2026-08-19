"""Daily digest generation (spec section 16-17), rendered as Markdown into
data/digests/YYYY-MM-DD.md. Built from the events newly ingested in a given
pipeline run, grouped by the same risk_level field the dashboard filters on
(Thấp/Trung bình/Cao, a 3-tier collapse of spec section 10's 5-tier model per
user request) -- not a separately score-thresholded set of bands, so a label
in the digest always matches what you can filter for in the dashboard."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

DIGESTS_DIR = Path(__file__).parent / "data" / "digests"

_BAND_ORDER = [
    ("Cao", "\U0001F534 CAO"),
    ("Trung bình", "\U0001F7E1 TRUNG BÌNH"),
    ("Thấp", "\U0001F7E2 THẤP"),
]


def _event_block(event: dict) -> str:
    vn_exposure = "None"
    if event["vietnam_direct"]:
        vn_exposure = "Direct"
    elif event["vietnam_indirect"]:
        vn_exposure = "Indirect / circumvention signal"

    lines = [
        f"**{event['title']}**",
        f"- Agency: {event['source_agency'] or 'n/a'}",
        f"- Legal basis: {event['legal_basis'] or 'n/a'} | Document type: {event['document_type']}",
        f"- Stage: {event['investigation_stage'] or 'unknown'}",
        f"- Vietnam exposure: {vn_exposure}" + (f" (also: {event['other_countries']})" if event["other_countries"] else ""),
        f"- Sectors: {event['sectors_matched'] or 'n/a'}",
        f"- Risk score: {event['risk_score']} ({event['risk_level']}) | Alert level: {event['alert_level']}",
        f"- Source: {event['source_url']}",
    ]
    if event.get("low_confidence"):
        lines.append("- ⚠️ Low-confidence match (kept for review, spec §20) — verify relevance before acting.")
    return "\n".join(lines)


def build_daily_digest(run_result: dict, digest_date: dt.date) -> str:
    events = run_result.get("new_events", [])

    header = [f"## US TRADE DAILY — {digest_date.isoformat()}", ""]
    header.append(
        f"Fetched {run_result['fetched']} documents ({run_result['start_date']} to {run_result['end_date']}), "
        f"{run_result['new_documents']} new, {run_result['new_alerts']} Cao-priority alerts."
    )
    header.append("")

    body = []
    for risk_level, label in _BAND_ORDER:
        band_events = [e for e in events if e["risk_level"] == risk_level]
        if not band_events:
            continue
        body.append(f"### {label}")
        body.append("")
        for e in sorted(band_events, key=lambda x: -int(x["risk_score"])):
            body.append(_event_block(e))
            body.append("")

    if not events:
        body.append("_No new documents matched this run._")

    return "\n".join(header + body)


def save_digest(content: str, digest_date: dt.date) -> Path:
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGESTS_DIR / f"{digest_date.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path
