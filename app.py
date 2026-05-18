"""
USEF Horse Rankings Dashboard
-----------------------------
A Streamlit dashboard for the `usef_horse_rankings` table in Supabase.

Features:
- Search by horse name or horse ID
- Filters: competition year (season), section, award category
- Sortable data table
- CSV export of filtered results
- Summary KPIs

Run:
    streamlit run app.py
"""

from __future__ import annotations

import os
from typing import List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TABLE_NAME = "usef_horse_rankings"
PAGE_SIZE = 500  # Smaller pages reduce risk of HTTP/2 stream resets on big tables
MAX_RETRIES = 4

load_dotenv()

st.set_page_config(
    page_title="USEF Horse Rankings",
    page_icon="🐎",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
def _get_secret(name: str) -> Optional[str]:
    """Look in st.secrets (Streamlit Cloud) first, then env vars / .env (local)."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        # st.secrets raises if no secrets file exists; that's fine locally.
        pass
    return os.environ.get(name)


@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    if not url or not key:
        st.error(
            "Missing SUPABASE_URL or SUPABASE_KEY.\n\n"
            "**Local:** add them to a `.env` file in this folder.\n"
            "**Streamlit Cloud:** add them under App Settings → Secrets."
        )
        st.stop()
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _fetch_page(sb, start: int, end: int):
    """Fetch one page with retry/backoff for transient network errors."""
    import time
    from httpx import RemoteProtocolError, ReadTimeout, ConnectError

    last_err: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            return (
                sb.table(TABLE_NAME)
                .select("*")
                .range(start, end)
                .execute()
            )
        except (RemoteProtocolError, ReadTimeout, ConnectError) as e:
            last_err = e
            sleep_s = 1.5 * (2 ** attempt)  # 1.5s, 3s, 6s, 12s
            time.sleep(sleep_s)
    # exhausted retries
    raise last_err  # type: ignore[misc]


@st.cache_data(ttl=300, show_spinner="Loading rankings from Supabase…")
def load_rankings() -> pd.DataFrame:
    """Load all rows from usef_horse_rankings, paginating past the row limit."""
    sb = get_client()
    rows: List[dict] = []
    offset = 0
    while True:
        resp = _fetch_page(sb, offset, offset + PAGE_SIZE - 1)
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Drop the primary-key `id` column from display (still exists in DB)
    if "id" in df.columns:
        df = df.drop(columns=["id"])

    # Coerce types
    for col in ("nat_points_good",):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("show_count", "competition_year"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("start_date", "end_date", "scraped_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    return df


# ---------------------------------------------------------------------------
# UI: Header
# ---------------------------------------------------------------------------
st.title("🐎 USEF Horse Rankings Dashboard")
st.caption(f"Source: Supabase table `{TABLE_NAME}`")

with st.spinner("Loading data…"):
    df = load_rankings()

if df.empty:
    st.warning("No rows returned from Supabase.")
    st.stop()

# ---------------------------------------------------------------------------
# UI: Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("🔎 Search & Filters")

# Autocomplete: type to filter the dropdown of all horse names
horse_names_available = sorted(
    df["horse_name"].dropna().astype(str).unique().tolist()
) if "horse_name" in df.columns else []
selected_horse = st.sidebar.selectbox(
    "Pick horse (autocomplete)",
    options=horse_names_available,
    index=None,
    placeholder="Start typing a horse name…",
    help="Type any part of the name to filter the list.",
)

# Free-text search (still works for horse IDs or partial matches)
search_query = st.sidebar.text_input(
    "Or free-text search (name or ID)",
    placeholder="e.g. ADLER or 4OwKggwWH28",
).strip()

# Season (competition_year)
years_available = sorted(
    [int(y) for y in df["competition_year"].dropna().unique()], reverse=True
) if "competition_year" in df.columns else []
selected_years = st.sidebar.multiselect(
    "Season (competition year)",
    options=years_available,
    default=years_available,
)

# Section
sections_available = sorted(df["section"].dropna().unique().tolist()) \
    if "section" in df.columns else []
selected_sections: Optional[List[str]] = st.sidebar.multiselect(
    "Section",
    options=sections_available,
    default=[],
    help="Leave empty to include all sections",
)

# Award category
awards_available = sorted(df["award_category"].dropna().unique().tolist()) \
    if "award_category" in df.columns else []
selected_awards: Optional[List[str]] = st.sidebar.multiselect(
    "Award category",
    options=awards_available,
    default=[],
    help="Leave empty to include all award categories",
)

# Min points slider
if "nat_points_good" in df.columns and df["nat_points_good"].notna().any():
    pmin = float(df["nat_points_good"].min())
    pmax = float(df["nat_points_good"].max())
    min_points = st.sidebar.slider(
        "Minimum national points",
        min_value=float(round(pmin, 2)),
        max_value=float(round(pmax, 2)),
        value=float(round(pmin, 2)),
        step=1.0,
    )
else:
    min_points = None

st.sidebar.divider()
if st.sidebar.button("🔄 Refresh data from Supabase"):
    load_rankings.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
filtered = df.copy()

if selected_horse:
    filtered = filtered[filtered["horse_name"].astype(str) == selected_horse]

if search_query:
    q = search_query.lower()
    name_match = filtered["horse_name"].astype(str).str.lower().str.contains(q, na=False) \
        if "horse_name" in filtered.columns else False
    id_match = filtered["horse_id"].astype(str).str.lower().str.contains(q, na=False) \
        if "horse_id" in filtered.columns else False
    filtered = filtered[name_match | id_match]

if selected_years and "competition_year" in filtered.columns:
    filtered = filtered[filtered["competition_year"].isin(selected_years)]

if selected_sections:
    filtered = filtered[filtered["section"].isin(selected_sections)]

if selected_awards:
    filtered = filtered[filtered["award_category"].isin(selected_awards)]

if min_points is not None and "nat_points_good" in filtered.columns:
    filtered = filtered[filtered["nat_points_good"].fillna(0) >= min_points]


# ---------------------------------------------------------------------------
# UI: KPIs
# ---------------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows", f"{len(filtered):,}", delta=f"of {len(df):,} total")
k2.metric(
    "Unique horses",
    f"{filtered['horse_id'].nunique():,}" if "horse_id" in filtered.columns else "—",
)
k3.metric(
    "Award categories",
    f"{filtered['award_category'].nunique():,}" if "award_category" in filtered.columns else "—",
)
if "nat_points_good" in filtered.columns and len(filtered):
    k4.metric("Avg national points", f"{filtered['nat_points_good'].mean():.2f}")
else:
    k4.metric("Avg national points", "—")

st.divider()


# ---------------------------------------------------------------------------
# UI: Results table
# ---------------------------------------------------------------------------
st.subheader(f"Results ({len(filtered):,})")

preferred_cols = [
    "competition_year",
    "horse_name",
    "horse_id",
    "section",
    "award_category",
    "nat_points_good",
    "show_count",
    "start_date",
    "end_date",
    "shows",
    "horse_link",
    "pdf_download_link",
    "scraped_at",
]
display_cols = [c for c in preferred_cols if c in filtered.columns] + \
               [c for c in filtered.columns if c not in preferred_cols]

display_df = filtered[display_cols].copy()

# Render with link columns when possible
column_config = {}
if "horse_link" in display_df.columns:
    column_config["horse_link"] = st.column_config.LinkColumn(
        "USEF page", display_text="Open"
    )
if "pdf_download_link" in display_df.columns:
    column_config["pdf_download_link"] = st.column_config.LinkColumn(
        "PDF report", display_text="PDF"
    )
if "nat_points_good" in display_df.columns:
    column_config["nat_points_good"] = st.column_config.NumberColumn(
        "Nat. points", format="%.2f"
    )

event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config=column_config,
    height=600,
    on_select="rerun",
    selection_mode="single-row",
    key="rankings_table",
)

# ---------------------------------------------------------------------------
# UI: Selected row details
# ---------------------------------------------------------------------------
selected_rows = event.selection.rows if hasattr(event, "selection") else []
if selected_rows:
    row_idx = selected_rows[0]
    row = display_df.iloc[row_idx]
    horse = row.get("horse_name", "—")
    st.success(f"Selected: **{horse}**  (row {row_idx + 1} of {len(display_df):,})")
    with st.expander("Row details", expanded=True):
        # Two-column display of the selected row
        c1, c2 = st.columns(2)
        items = list(row.items())
        half = (len(items) + 1) // 2
        for k, v in items[:half]:
            c1.markdown(f"**{k}**: {v}")
        for k, v in items[half:]:
            c2.markdown(f"**{k}**: {v}")
else:
    st.caption("👆 Click any row to highlight it and see its details.")

# ---------------------------------------------------------------------------
# UI: CSV download
# ---------------------------------------------------------------------------
csv_bytes = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇️  Download filtered results as CSV",
    data=csv_bytes,
    file_name="usef_horse_rankings_filtered.csv",
    mime="text/csv",
    use_container_width=False,
)

st.caption(
    "Tip: click any column header in the table above to sort. "
    "Filters apply live and the CSV reflects the current filtered view."
)
