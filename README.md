# US Trade Policy Monitor

Tracks US trade-policy actions (AD/CVD, Section 232/301/201/337, IEEPA, UFLPA,
BIS export controls, OFAC sanctions) that could affect Vietnam, scores them
for Vietnam/sector/company exposure, and surfaces HIGH/CRITICAL items in a
Streamlit dashboard.

Built from `US_Trade_Policy_Monitoring_AI_Coding_Spec_v1.0.md` — this is the
**Phase 1 MVP** of that spec (see "Scope" below for what's deferred).

## Data source

[Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1)
(`federalregister.gov/api/v1`) — free, public, no API key. Nearly everything
DOC/ITA, USTR, USITC, BIS, OFAC, CBP, and the White House do formally gets
published there, so one connector (`federal_register.py`) covers most of the
spec's Tier-A sources instead of separate scrapers per agency.

## Setup

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Running

```
python run_daily.py             # incremental fetch since last run (or last 14 days on first run)
streamlit run app.py            # dashboard at http://localhost:8501
```

`run_daily.py --start 2026-01-01 --end 2026-08-19` runs an explicit date
range (useful for a one-time backfill).

## How the daily automation works

A Claude Code scheduled cloud agent runs daily: pulls this repo, runs
`python run_daily.py`, commits the updated `data/` files, pushes. The
Streamlit dashboard (local or hosted) just reads whatever is in `data/` at
the time it's loaded — `git pull` before checking it if running locally.

Data is stored as CSV files under `data/`, not SQLite — a cloud agent can't
touch a local SQLite file directly, and CSVs commit cleanly (append-mostly,
human-diffable) where a daily-rewritten SQLite binary would bloat the repo.

## Editing the watchlists

No code changes needed for:
- `config/legal_basis.yaml` — legal-basis keyword sets (AD/CVD, Section
  232/301/201/337, IEEPA, UFLPA, BIS, OFAC, Special 301) and stage-detection phrases
- `config/countries.yaml` — country watchlist + circumvention/transshipment terms
- `config/sectors.yaml` — sector keyword map
- `data/companies.csv` — company exposure DB. Seeded with ticker + sector
  only for well-known names (VHC, ANV, MPC, TNG, MSH, TCM, HPG, NKG, HSG,
  PTB, GDT, DGC, DPM, DCM). **HS codes and US revenue exposure are left
  blank on purpose** — fill them in yourself; nothing here fabricates
  financial figures.

## Scope (Phase 1 MVP)

**In:** Federal Register agency-filtered pulls (DOC/ITA, USTR, USITC, BIS,
OFAC, CBP) + Presidential Documents + Public Inspection (early-warning) +
a no-miss term-search sweep (spec §19, condensed). Rule-based classification:
legal basis, document type, investigation stage, Vietnam exposure
(direct/indirect/global/third-country), sector/company keyword matching,
risk scoring (spec §10-11), alert priority (spec §12), case-level dedup
(spec §13). Daily Markdown digest. Streamlit dashboard.

**Deferred (see spec §32 Phase 2-4):**
- Dedicated USTR/USITC/CBP/BIS/OFAC scrapers beyond what Federal Register's
  agency filter covers — only add if a specific gap shows up.
- LLM-based extraction (spec §25), PDF/OCR parsing (spec §24).
- Event relationship graph (spec §14), change detection (spec §27), full
  human-review workflow (spec §26) — currently just a `low_confidence` flag.
- Email/Slack alerts (dashboard-only for now), weekly digest automation,
  backtesting (spec §30).
- Product/HS-code/tariff-rate/effective-date/comment-deadline extraction —
  Federal Register's title+abstract don't reliably contain these; needs
  full-text parsing (Phase 2/3).

## Known limitation

Classification is keyword-based against document **title + abstract only**
(no full-text/PDF parsing yet), so nuanced or implicitly-worded documents can
be missed or misclassified — treat this as a triage/early-warning layer, not
a substitute for reading the source document on any HIGH/CRITICAL item.
