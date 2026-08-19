"""
US Trade Policy Monitor -- Vietnam exposure dashboard.
Data source: Federal Register API (federalregister.gov), refreshed daily by
a scheduled pipeline run (see run_daily.py / README.md).

Run with: streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="US Trade Policy Monitor", layout="wide")

DATA_DIR = Path(__file__).parent / "data"
DIGESTS_DIR = DATA_DIR / "digests"

@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame:
    path = DATA_DIR / "events.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in ("risk_score",):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
    for bool_col in ("vietnam_direct", "vietnam_indirect", "low_confidence"):
        df[bool_col] = df[bool_col].astype(str).str.lower().isin(["true", "1"])
    return df


@st.cache_data(ttl=300)
def load_event_company() -> pd.DataFrame:
    path = DATA_DIR / "event_company.csv"
    if not path.exists():
        return pd.DataFrame(columns=["event_id", "ticker"])
    return pd.read_csv(path, dtype=str).fillna("")


@st.cache_data(ttl=300)
def load_companies() -> pd.DataFrame:
    path = DATA_DIR / "companies.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def vietnam_exposure_label(row) -> str:
    if row["vietnam_direct"]:
        return "Direct"
    if row["vietnam_indirect"]:
        return "Indirect"
    return "None"


st.title("US Trade Policy Monitor")
st.caption(
    "Tracks US trade-policy actions (AD/CVD, Section 232/301/201/337, IEEPA, UFLPA, BIS, OFAC) "
    "via the Federal Register API, scored for Vietnam exposure. Rule-based classification (no LLM in this MVP) — "
    "verify Cao-priority items against the source before acting. Product/HS code/tariff-rate/effective-date "
    "fields are not yet extracted (Phase 2/3)."
)

tab_dashboard, tab_digest, tab_companies = st.tabs(["📋 Dashboard", "📰 Daily Digest", "🏢 Companies"])

# ------------------------------------------------------------- DASHBOARD TAB
with tab_dashboard:
    events = load_events()

    if events.empty:
        st.info("No data yet. Run `python run_daily.py` to fetch the first batch.")
    else:
        event_company = load_event_company()
        companies_by_event = event_company.groupby("event_id")["ticker"].apply(lambda s: ", ".join(sorted(set(s))))
        events = events.merge(companies_by_event.rename("companies"), on="event_id", how="left")
        events["companies"] = events["companies"].fillna("")
        events["vietnam_exposure"] = events.apply(vietnam_exposure_label, axis=1)

        st.subheader("Filters")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            min_date = events["publication_date"].min()
            max_date = events["publication_date"].max()
            if pd.isna(min_date) or pd.isna(max_date):
                date_range = None
            else:
                date_range = st.date_input(
                    "Publication date range", value=(min_date.date(), max_date.date()),
                    min_value=min_date.date(), max_value=max_date.date(),
                )
        with f2:
            all_legal_basis = sorted(set(
                lb.strip() for row in events["legal_basis"] for lb in row.split(";") if lb.strip()
            ))
            selected_legal_basis = st.multiselect("Legal basis", all_legal_basis)
        with f3:
            risk_levels = ["Cao", "Trung bình", "Thấp"]
            selected_risk = st.multiselect("Risk level", risk_levels)
        with f4:
            vn_exposure_filter = st.multiselect("Vietnam exposure", ["Direct", "Indirect", "None"])

        f5, f6, f7 = st.columns(3)
        with f5:
            all_sectors = sorted(set(
                s.strip() for row in events["sectors_matched"] for s in row.split(";") if s.strip()
            ))
            selected_sectors = st.multiselect("Sector", all_sectors)
        with f6:
            all_stages = sorted(s for s in events["investigation_stage"].unique() if s)
            selected_stages = st.multiselect("Stage", all_stages)
        with f7:
            all_companies = sorted(event_company["ticker"].unique())
            selected_companies = st.multiselect("Company", all_companies)
        hide_low_confidence = st.checkbox("Hide low-confidence matches", value=True)

        filtered = events.copy()
        if date_range and len(date_range) == 2:
            start, end = date_range
            filtered = filtered[
                (filtered["publication_date"].dt.date >= start) & (filtered["publication_date"].dt.date <= end)
            ]
        if selected_legal_basis:
            filtered = filtered[filtered["legal_basis"].apply(
                lambda v: any(lb in v for lb in selected_legal_basis)
            )]
        if selected_risk:
            filtered = filtered[filtered["risk_level"].isin(selected_risk)]
        if vn_exposure_filter:
            filtered = filtered[filtered["vietnam_exposure"].isin(vn_exposure_filter)]
        if selected_sectors:
            filtered = filtered[filtered["sectors_matched"].apply(
                lambda v: any(s in v for s in selected_sectors)
            )]
        if selected_stages:
            filtered = filtered[filtered["investigation_stage"].isin(selected_stages)]
        if selected_companies:
            filtered = filtered[filtered["companies"].apply(
                lambda v: any(c in v.split(", ") for c in selected_companies)
            )]
        if hide_low_confidence:
            filtered = filtered[~filtered["low_confidence"]]

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Events shown", len(filtered))
        c2.metric("Cao", int((filtered["risk_level"] == "Cao").sum()))
        c3.metric("Trung bình", int((filtered["risk_level"] == "Trung bình").sum()))
        c4.metric("Direct Vietnam exposure", int((filtered["vietnam_exposure"] == "Direct").sum()))

        display_cols = {
            "publication_date": "Date",
            "legal_basis": "Legal Basis",
            "document_type": "Action",
            "vietnam_exposure": "VN Exposure",
            "sectors_matched": "Sector",
            "investigation_stage": "Stage",
            "risk_score": "Risk Score",
            "risk_level": "Risk",
            "companies": "Companies",
            "title": "Title",
            "source_url": "Source",
        }
        table = filtered.sort_values("publication_date", ascending=False)[list(display_cols.keys())]
        table = table.rename(columns=display_cols)
        table["Date"] = table["Date"].dt.strftime("%Y-%m-%d")

        st.dataframe(
            table,
            width="stretch",
            hide_index=True,
            column_config={
                "Source": st.column_config.LinkColumn("Source", display_text="Open"),
                "Risk Score": st.column_config.NumberColumn(format="%d"),
                "Title": st.column_config.TextColumn(width="large"),
            },
        )

        csv_bytes = table.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download filtered table (CSV)", csv_bytes, "us_trade_events.csv", "text/csv")

# ------------------------------------------------------------------- DIGEST TAB
with tab_digest:
    if not DIGESTS_DIR.exists() or not list(DIGESTS_DIR.glob("*.md")):
        st.info("No digest yet. Run `python run_daily.py` to generate the first one.")
    else:
        digest_files = sorted(DIGESTS_DIR.glob("*.md"), reverse=True)
        labels = [f.stem for f in digest_files]
        selected = st.selectbox("Digest date", labels)
        chosen_path = DIGESTS_DIR / f"{selected}.md"
        st.markdown(chosen_path.read_text(encoding="utf-8"))

# ---------------------------------------------------------------- COMPANIES TAB
with tab_companies:
    companies = load_companies()
    st.caption(
        "Company exposure DB (spec §5) — seeded with ticker + sector only. HS codes and US revenue "
        "exposure are left blank deliberately (not fabricated); edit data/companies.csv to add them."
    )
    if companies.empty:
        st.info("No companies configured yet. Add rows to data/companies.csv.")
    else:
        sector_filter = st.multiselect("Filter by sector", sorted(companies["sector"].unique()))
        shown = companies[companies["sector"].isin(sector_filter)] if sector_filter else companies
        st.dataframe(shown, width="stretch", hide_index=True)
