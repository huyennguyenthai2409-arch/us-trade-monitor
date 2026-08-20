"""Exports data/*.csv into docs/data/*.json for the static site (docs/index.html).

Standalone and re-runnable at any time: reads only from data/*.csv on disk,
never from a live pipeline run, no network calls. Reuses summarize.py so the
site's Summary column is byte-for-byte the same text app.py shows -- this
script must never reimplement logic that already lives elsewhere.

Run manually: python export_site_data.py
Wired into run_daily.py so the daily cloud commit keeps docs/data/ fresh.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

import summarize

DATA_DIR = Path(__file__).parent / "data"
DIGESTS_DIR = DATA_DIR / "digests"
DOCS_DATA_DIR = Path(__file__).parent / "docs" / "data"

TOP_EVENTS_COUNT = 8
TOP_SECTORS_COUNT = 8

LEGAL_BASIS_LABELS = {
    "AD_CVD": "AD/CVD",
    "SECTION_232": "Section 232",
    "SECTION_301": "Section 301",
    "SECTION_201": "Section 201",
    "SECTION_337": "Section 337",
    "IEEPA_PRESIDENTIAL": "IEEPA / Presidential",
    "UFLPA_FORCED_LABOR": "UFLPA / Forced Labor",
    "BIS_EXPORT_CONTROLS": "BIS Export Controls",
    "OFAC_SANCTIONS": "OFAC Sanctions",
    "SPECIAL_301_IP": "Special 301 (IP)",
}


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


def load_events() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "events.csv", dtype=str).fillna("")
    df["risk_score"] = pd.to_numeric(df["risk_score"], errors="coerce").fillna(0).astype(int)
    for bool_col in ("vietnam_direct", "vietnam_indirect", "low_confidence"):
        df[bool_col] = df[bool_col].astype(str).str.lower().isin(["true", "1"])
    if "countries_named" not in df.columns:
        df["countries_named"] = ""
    return df


def load_abstracts() -> dict[str, str]:
    path = DATA_DIR / "documents.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return dict(zip(df["document_id"], df["abstract"]))


def load_companies_by_event() -> dict[str, list[str]]:
    path = DATA_DIR / "event_company.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return {event_id: sorted(set(grp["ticker"])) for event_id, grp in df.groupby("event_id")}


def load_companies() -> list[dict]:
    path = DATA_DIR / "companies.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    return [
        {"ticker": r["ticker"], "company_name": r["company_name"], "sector": r["sector"], "subsector": r["subsector"]}
        for r in df.to_dict("records")
    ]


def load_state() -> dict:
    path = DATA_DIR / "state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def vietnam_exposure_label(direct: bool, indirect: bool) -> str:
    if direct:
        return "Direct"
    if indirect:
        return "Indirect"
    return "None"


def build_event_records(events_df: pd.DataFrame, abstracts: dict, companies_by_event: dict) -> list[dict]:
    records = []
    for row in events_df.to_dict("records"):
        legal_basis = _split(row["legal_basis"])
        abstract = abstracts.get(row["document_id"], "")
        rate = summarize.extract_rate(f"{row['title']} {abstract}", legal_basis)
        summary = summarize.short_summary(row["title"], abstract, rate, max_chars=500)
        records.append({
            "id": row["event_id"],
            "date": row["publication_date"],
            "legal_basis": legal_basis,
            "action": row["document_type"],
            "vn_exposure": vietnam_exposure_label(row["vietnam_direct"], row["vietnam_indirect"]),
            "countries": _split(row["countries_named"]),
            "sectors": _split(row["sectors_matched"]),
            "stage": row["investigation_stage"],
            "risk_score": row["risk_score"],
            "risk_level": row["risk_level"],
            "low_confidence": row["low_confidence"],
            "companies": companies_by_event.get(row["event_id"], []),
            "summary": summary,
            "source": row["source_url"],
        })
    return records


def build_meta(events: list[dict], event_company_tickers: list[str], state: dict) -> dict:
    relevant = [e for e in events if not e["low_confidence"]]
    dates = sorted(e["date"] for e in events if e["date"])

    legal_basis_facets = sorted(
        {b for e in events for b in e["legal_basis"]},
        key=lambda k: LEGAL_BASIS_LABELS.get(k, k),
    )
    sector_facets = sorted({s for e in events for s in e["sectors"]})
    stage_facets = sorted({e["stage"] for e in events if e["stage"]})

    high_by_basis: dict[str, int] = {}
    for e in events:
        if e["risk_level"] != "High":
            continue
        for b in e["legal_basis"] or ["(unspecified)"]:
            high_by_basis[b] = high_by_basis.get(b, 0) + 1
    top_legal_basis_high = [
        {"key": k, "label": LEGAL_BASIS_LABELS.get(k, k), "count": v}
        for k, v in sorted(high_by_basis.items(), key=lambda kv: -kv[1])
    ]

    top_events = sorted(relevant, key=lambda e: -e["risk_score"])[:TOP_EVENTS_COUNT]
    top_events = [
        {k: e[k] for k in ("id", "date", "legal_basis", "action", "vn_exposure", "countries", "sectors", "risk_score", "risk_level", "summary", "source")}
        for e in top_events
    ]

    sector_counts: dict[str, int] = {}
    for e in relevant:
        for s in e["sectors"]:
            sector_counts[s] = sector_counts.get(s, 0) + 1
    top_sectors = [
        {"sector": k, "count": v}
        for k, v in sorted(sector_counts.items(), key=lambda kv: -kv[1])[:TOP_SECTORS_COUNT]
    ]

    week_counts: dict[str, dict] = {}
    for e in relevant:
        if not e["date"]:
            continue
        d = dt.date.fromisoformat(e["date"])
        week_start = (d - dt.timedelta(days=d.weekday())).isoformat()
        bucket = week_counts.setdefault(week_start, {"week_start": week_start, "count": 0, "high_count": 0})
        bucket["count"] += 1
        if e["risk_level"] == "High":
            bucket["high_count"] += 1
    weekly_counts = [week_counts[k] for k in sorted(week_counts)]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "last_run_date": state.get("last_run_date"),
        "last_run_at": state.get("last_run_at"),
        "total_events": len(events),
        "shown_default": len(relevant),
        "high_count": sum(1 for e in relevant if e["risk_level"] == "High"),
        "medium_count": sum(1 for e in relevant if e["risk_level"] == "Medium"),
        "low_count": sum(1 for e in relevant if e["risk_level"] == "Low"),
        "direct_vn_count": sum(1 for e in relevant if e["vn_exposure"] == "Direct"),
        "date_range": {"min": dates[0] if dates else None, "max": dates[-1] if dates else None},
        "facets": {
            "legal_basis": [{"key": k, "label": LEGAL_BASIS_LABELS.get(k, k)} for k in legal_basis_facets],
            "sectors": sector_facets,
            "stages": stage_facets,
            "companies": sorted(set(event_company_tickers)),
        },
        "top_legal_basis_high": top_legal_basis_high,
        "top_events": top_events,
        "top_sectors": top_sectors,
        "weekly_counts": weekly_counts,
    }


# ----------------------------------------------------------- digest parsing
# Parses digest.py's own fixed output format (see digest.py's _event_block) --
# this is decoding a format we control, not guessing at an external one.

_HEADER_RE = re.compile(r"^## US TRADE DAILY — (\d{4}-\d{2}-\d{2})", re.MULTILINE)
_SUMMARY_RE = re.compile(
    r"^Fetched (\d+) documents \(([\d-]+) to ([\d-]+)\), (\d+) new, (\d+) High-priority alerts\.",
    re.MULTILINE,
)
_BAND_RE = re.compile(r"^### \S+ (LOW|MEDIUM|HIGH)$", re.MULTILINE)
_EVENT_RE = re.compile(
    r"^\*\*(?P<title>.+?)\*\*\n"
    r"- Agency: (?P<agency>.*)\n"
    r"- Legal basis: (?P<legal_basis>.*) \| Document type: (?P<doc_type>.*)\n"
    r"- Stage: (?P<stage>.*)\n"
    r"- Vietnam exposure: (?P<vn>.*)\n"
    r"- Sectors: (?P<sectors>.*)\n"
    r"- Risk score: (?P<score>\d+) \((?P<level>\w+)\) \| Alert level: (?P<alert>\w+)\n"
    r"- Source: (?P<url>\S+)",
    re.MULTILINE,
)


def parse_digest(text: str) -> dict | None:
    header = _HEADER_RE.search(text)
    summary = _SUMMARY_RE.search(text)
    if not header or not summary:
        return None

    bands = [(m.group(1), m.start()) for m in _BAND_RE.finditer(text)]

    def band_for(pos: int) -> str:
        if not bands or pos < bands[0][1]:
            print(f"WARNING: digest event at offset {pos} precedes any band header, defaulting to LOW")
            return "LOW"
        current = "LOW"
        for label, start in bands:
            if start <= pos:
                current = label
            else:
                break
        return current

    events = []
    for m in _EVENT_RE.finditer(text):
        legal_basis = [] if m.group("legal_basis") == "n/a" else _split(m.group("legal_basis"))
        events.append({
            "title": m.group("title").strip(),
            "agency": m.group("agency"),
            "legal_basis": legal_basis,
            "doc_type": m.group("doc_type"),
            "stage": None if m.group("stage") == "unknown" else m.group("stage"),
            "vn_exposure": m.group("vn"),
            "sectors": [] if m.group("sectors") == "n/a" else _split(m.group("sectors")),
            "risk_score": int(m.group("score")),
            "risk_level": m.group("level"),
            "alert_level": m.group("alert"),
            "source": m.group("url"),
            "band": band_for(m.start()),
        })

    return {
        "date": header.group(1),
        "fetched": int(summary.group(1)),
        "start_date": summary.group(2),
        "end_date": summary.group(3),
        "new_documents": int(summary.group(4)),
        "new_alerts": int(summary.group(5)),
        "events": events,
    }


def build_digests() -> dict[str, dict]:
    out = {}
    if not DIGESTS_DIR.exists():
        return out
    for path in sorted(DIGESTS_DIR.glob("*.md")):
        parsed = parse_digest(path.read_text(encoding="utf-8"))
        if parsed is None:
            print(f"WARNING: could not parse digest {path.name}, skipping")
            continue
        out[parsed["date"]] = parsed
    return out


def main() -> None:
    events_df = load_events()
    abstracts = load_abstracts()
    companies_by_event = load_companies_by_event()
    companies = load_companies()
    state = load_state()

    event_records = build_event_records(events_df, abstracts, companies_by_event)
    event_company_tickers = [t for tickers in companies_by_event.values() for t in tickers]
    meta = build_meta(event_records, event_company_tickers, state)
    digests = build_digests()

    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DATA_DIR / "events.json").write_text(
        json.dumps(event_records, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    (DOCS_DATA_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DOCS_DATA_DIR / "companies.json").write_text(
        json.dumps(companies, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    digests_dir = DOCS_DATA_DIR / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    for date, parsed in digests.items():
        (digests_dir / f"{date}.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (DOCS_DATA_DIR / "digests_index.json").write_text(
        json.dumps(sorted(digests.keys(), reverse=True)), encoding="utf-8"
    )

    print(f"Exported {len(event_records)} events, {len(digests)} digests to {DOCS_DATA_DIR}")


if __name__ == "__main__":
    main()
