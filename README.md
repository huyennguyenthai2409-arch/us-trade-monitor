# US Trade Policy Monitor

Tracks US trade-policy actions (AD/CVD, Section 232/301/201/337, IEEPA, UFLPA,
BIS export controls, OFAC sanctions) that could affect Vietnam, scores them
for Vietnam/sector/company exposure, and surfaces High-priority items in two
UIs backed by the same `data/` CSVs:
- **`docs/`** — a static site (colors/type/layout ported from the "Peers
  Holdings" design system), hosted on GitHub Pages, fed by
  `export_site_data.py`. This is the primary UI going forward.
- **`app.py`** — the original Streamlit dashboard, kept running in parallel
  as a fallback / raw-data view.

Investigation stage and risk level use a simplified vocabulary (collapsed
from the spec's original 9-stage / 5-tier model, per user request):
- **Stage** (4): Initiation → Review (of an existing order) → Preliminary → Final
- **Risk level** (3): Low / Medium / High

Built from `US_Trade_Policy_Monitoring_AI_Coding_Spec_v1.0.md` — this is the
**Phase 1 MVP** of that spec (see "Scope" below for what's deferred).

## Data sources

- **[Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1)**
  (`federal_register.py`) — free, public, no API key. Nearly everything
  DOC/ITA, USTR, USITC, BIS, OFAC, CBP, and the White House do *formally*
  gets published there eventually, so this one connector covers most of the
  spec's Tier-A sources. Its downside: formal publication regularly lags the
  actual news by days.
- **White House** (`whitehouse.py`) — scrapes
  `whitehouse.gov/presidential-actions/`. An EO/proclamation/memorandum
  typically appears here the day it's signed, well before its Federal
  Register filing.
- **USTR** (`ustr.py`) — scrapes USTR's press-releases page. Section
  301/232 actions and tariff/trade-deal announcements are often first (or
  only) announced as a press release, not a Federal Register notice.
- **Commerce** (`commerce.py`) — scrapes `trade.gov` (International Trade
  Administration) press releases. `commerce.gov` itself sits behind a
  Cloudflare JS challenge no plain scraper can pass, so ITA's own site is
  the practical Commerce source.

None of these three have a public API, so they're plain HTML scrapers
(`web_scrape_common.py` has the shared fetch/parse helpers) — more fragile
than the Federal Register connector by nature, which is why `pipeline.py`
wraps each of their `fetch_all()` calls in its own try/except: one of them
breaking (site redesign, temporary block) prints a warning and skips that
source for the run rather than failing the whole daily pipeline. All three
normalize into the exact same document shape `federal_register.py`
produces, so nothing downstream (classify/exposure/scoring/dedupe/site
export) needed to change.

## Setup

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Running

```
python run_daily.py             # incremental fetch since last run (or last 14 days on first run)
python export_site_data.py      # regenerate docs/data/*.json from data/*.csv (run_daily.py also calls this)
python -m http.server 8000 --directory docs   # static site at http://localhost:8000
streamlit run app.py            # Streamlit fallback UI at http://localhost:8501
```

`run_daily.py --start 2026-01-01 --end 2026-08-19` runs an explicit date
range (useful for a one-time backfill).

## The static site (`docs/`)

`export_site_data.py` reads `data/*.csv` (never a live pipeline run) and
writes `docs/data/events.json`, `meta.json`, `companies.json`,
`digests_index.json`, and `docs/data/digests/<date>.json` — plain static
files, no backend. `docs/index.html` + `docs/assets/js/*.js` (vanilla ES
modules, no bundler/framework) fetch those and do all filtering/sorting
client-side. Hosted on GitHub Pages: repo Settings → Pages → Deploy from a
branch → `main` / `/docs`. Every push to `main` that touches `docs/`
auto-republishes.

**GH Pages footgun:** the site serves under `/us-trade-monitor/`, not `/` —
all `fetch()` calls in the JS use relative paths (`./data/events.json`), not
root-relative ones.

## How the daily automation works

A Claude Code scheduled cloud agent runs daily: pulls this repo, runs
`python run_daily.py` (which also regenerates `docs/data/`), commits the
updated `data/` and `docs/data/` files, pushes. The Streamlit dashboard
(local or hosted) and the GitHub Pages site both just read whatever is
committed at the time they're loaded — `git pull` before checking locally.

Data is stored as CSV files under `data/`, not SQLite — a cloud agent can't
touch a local SQLite file directly, and CSVs commit cleanly (append-mostly,
human-diffable) where a daily-rewritten SQLite binary would bloat the repo.
`docs/data/*.json` are generated from those CSVs and committed alongside
them for the same reason (the static site has no backend to compute from
CSVs at request time).

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
a no-miss term-search sweep (spec §19, condensed) + dedicated White House /
USTR / Commerce (ITA) scrapers for early-warning coverage ahead of formal
Federal Register publication. Rule-based classification:
legal basis, document type, investigation stage, Vietnam exposure
(direct/indirect/global/third-country), sector/company keyword matching,
risk scoring (spec §10-11), alert priority (spec §12), case-level dedup
(spec §13). Daily Markdown digest. Streamlit dashboard.

**Deferred (see spec §32 Phase 2-4):**
- Dedicated USITC/CBP/BIS/OFAC scrapers beyond what Federal Register's
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
a substitute for reading the source document on any High-priority item.

The dashboard table doesn't show the source agency column (removed per user
request) — the underlying data still has it (`data/events.csv`'s
`source_agency` column, and each digest entry), just not surfaced in the UI.
