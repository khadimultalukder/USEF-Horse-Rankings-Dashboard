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
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Custom styles — animated KPI cards, detail card, table row styling
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&display=swap');

    /* ---------- Animated KPI cards ---------- */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1rem;
        margin: 0.5rem 0 1.25rem 0;
    }
    @media (max-width: 900px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    }
    .kpi-card {
        position: relative;
        padding: 1.1rem 1.25rem 1rem 1.25rem;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(236, 72, 153, 0.06) 100%),
                    rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(148, 163, 184, 0.18);
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03);
        transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1),
                    box-shadow 0.28s cubic-bezier(0.4, 0, 0.2, 1),
                    border-color 0.28s ease;
        overflow: hidden;
        animation: kpi-fade-in 0.55s ease-out both;
    }
    @media (prefers-color-scheme: dark) {
        .kpi-card {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.10) 0%, rgba(236, 72, 153, 0.08) 100%),
                        rgba(30, 41, 59, 0.55);
            border-color: rgba(148, 163, 184, 0.18);
        }
    }
    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: var(--accent, linear-gradient(90deg, #6366f1, #a855f7));
        opacity: 0.95;
    }
    .kpi-card::after {
        content: '';
        position: absolute;
        top: -40%; right: -20%;
        width: 160px; height: 160px;
        background: radial-gradient(circle, var(--glow, rgba(99,102,241,0.25)) 0%, transparent 70%);
        filter: blur(20px);
        opacity: 0.6;
        pointer-events: none;
        transition: opacity 0.3s ease;
    }
    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 14px 28px rgba(15, 23, 42, 0.12), 0 0 0 1px rgba(99, 102, 241, 0.25);
        border-color: rgba(99, 102, 241, 0.4);
    }
    .kpi-card:hover::after { opacity: 1; }

    .kpi-card.kpi-indigo::before { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
    .kpi-card.kpi-indigo { --glow: rgba(99, 102, 241, 0.30); }
    .kpi-card.kpi-cyan::before   { background: linear-gradient(90deg, #06b6d4, #22d3ee); }
    .kpi-card.kpi-cyan   { --glow: rgba(34, 211, 238, 0.30); }
    .kpi-card.kpi-pink::before   { background: linear-gradient(90deg, #ec4899, #f472b6); }
    .kpi-card.kpi-pink   { --glow: rgba(236, 72, 153, 0.30); }
    .kpi-card.kpi-amber::before  { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
    .kpi-card.kpi-amber  { --glow: rgba(245, 158, 11, 0.30); }

    .kpi-icon {
        font-size: 1.35rem;
        line-height: 1;
        margin-bottom: 0.4rem;
        display: inline-block;
        animation: kpi-icon-pop 0.7s ease-out both;
    }
    .kpi-label {
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748b;
        margin-bottom: 0.3rem;
    }
    .kpi-value {
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        font-size: 1.85rem;
        font-weight: 700;
        line-height: 1.1;
        color: #0f172a;
    }
    @media (prefers-color-scheme: dark) {
        .kpi-value { color: #f8fafc; }
    }
    .kpi-sub {
        font-size: 0.72rem;
        color: #94a3b8;
        margin-top: 0.3rem;
    }

    @keyframes kpi-fade-in {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes kpi-icon-pop {
        0%   { opacity: 0; transform: scale(0.6) rotate(-10deg); }
        60%  { opacity: 1; transform: scale(1.15) rotate(4deg); }
        100% { opacity: 1; transform: scale(1) rotate(0); }
    }
    /* Stagger each card */
    .kpi-card:nth-child(1) { animation-delay: 0.00s; }
    .kpi-card:nth-child(2) { animation-delay: 0.08s; }
    .kpi-card:nth-child(3) { animation-delay: 0.16s; }
    .kpi-card:nth-child(4) { animation-delay: 0.24s; }

    /* ---------- Detail card (selected row) ---------- */
    .detail-card {
        padding: 1rem 1.25rem;
        margin: 0.75rem 0 0.25rem 0;
        border-radius: 14px;
        border: 1px solid rgba(168, 85, 247, 0.35);
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.10) 0%, rgba(236, 72, 153, 0.10) 100%);
        animation: kpi-fade-in 0.4s ease-out both;
    }
    .detail-card .detail-title {
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        margin: 0 0 0.15rem 0;
    }
    .detail-card .detail-sub {
        font-size: 0.82rem;
        color: #64748b;
    }

    /* ---------- DataFrame row styling ---------- */
    [data-testid="stDataFrame"] {
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid rgba(148, 163, 184, 0.18);
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    /* Zebra rows */
    [data-testid="stDataFrame"] [role="row"]:nth-child(even) > [role="gridcell"] {
        background: rgba(99, 102, 241, 0.04) !important;
    }
    /* Hover highlight */
    [data-testid="stDataFrame"] [role="row"]:hover > [role="gridcell"] {
        background: rgba(168, 85, 247, 0.10) !important;
        cursor: pointer;
        transition: background 0.15s ease;
    }
    /* Header */
    [data-testid="stDataFrame"] [role="columnheader"] {
        background: linear-gradient(180deg, rgba(99, 102, 241, 0.10), rgba(99, 102, 241, 0.04)) !important;
        font-weight: 600 !important;
        color: #1e293b !important;
        border-bottom: 1px solid rgba(99, 102, 241, 0.25) !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stDataFrame"] [role="columnheader"] {
            color: #e2e8f0 !important;
            background: linear-gradient(180deg, rgba(99, 102, 241, 0.18), rgba(99, 102, 241, 0.08)) !important;
        }
        [data-testid="stDataFrame"] [role="row"]:nth-child(even) > [role="gridcell"] {
            background: rgba(99, 102, 241, 0.07) !important;
        }
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


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
# UI: Filters (on main page)
# ---------------------------------------------------------------------------
with st.expander("🔎 Search & Filters", expanded=True):
    # Row 1: horse picker + free-text search
    r1c1, r1c2 = st.columns([1, 1])
    horse_names_available = sorted(
        df["horse_name"].dropna().astype(str).unique().tolist()
    ) if "horse_name" in df.columns else []
    with r1c1:
        selected_horse = st.selectbox(
            "Pick horse (autocomplete)",
            options=horse_names_available,
            index=None,
            placeholder="Start typing a horse name…",
            help="Type any part of the name to filter the list.",
        )
    with r1c2:
        search_query = st.text_input(
            "Or free-text search (name or ID)",
            placeholder="e.g. ADLER or 4OwKggwWH28",
        ).strip()

    # Row 2: years + sections + award category
    r2c1, r2c2, r2c3 = st.columns(3)
    years_available = sorted(
        [int(y) for y in df["competition_year"].dropna().unique()], reverse=True
    ) if "competition_year" in df.columns else []
    with r2c1:
        selected_years = st.multiselect(
            "Season (competition year)",
            options=years_available,
            default=years_available,
        )
    sections_available = sorted(df["section"].dropna().unique().tolist()) \
        if "section" in df.columns else []
    with r2c2:
        selected_sections: Optional[List[str]] = st.multiselect(
            "Section",
            options=sections_available,
            default=[],
            help="Leave empty to include all sections",
        )
    awards_available = sorted(df["award_category"].dropna().unique().tolist()) \
        if "award_category" in df.columns else []
    with r2c3:
        selected_awards: Optional[List[str]] = st.multiselect(
            "Award category",
            options=awards_available,
            default=[],
            help="Leave empty to include all award categories",
        )

    # Row 3: min points slider + refresh button
    r3c1, r3c2 = st.columns([3, 1])
    if "nat_points_good" in df.columns and df["nat_points_good"].notna().any():
        pmin = float(df["nat_points_good"].min())
        pmax = float(df["nat_points_good"].max())
        with r3c1:
            min_points = st.slider(
                "Minimum national points",
                min_value=float(round(pmin, 2)),
                max_value=float(round(pmax, 2)),
                value=float(round(pmin, 2)),
                step=1.0,
            )
    else:
        min_points = None
        with r3c1:
            st.caption("No national points data available.")
    with r3c2:
        st.write("")  # spacer to align with slider
        st.write("")
        if st.button("🔄 Refresh data", use_container_width=True):
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
# UI: KPIs (animated cards)
# ---------------------------------------------------------------------------
_kpi_rows = len(filtered)
_kpi_total = len(df)
_kpi_unique = f"{filtered['horse_id'].nunique():,}" if "horse_id" in filtered.columns else "—"
_kpi_awards = f"{filtered['award_category'].nunique():,}" if "award_category" in filtered.columns else "—"
if "nat_points_good" in filtered.columns and len(filtered) and filtered["nat_points_good"].notna().any():
    _kpi_avg = f"{filtered['nat_points_good'].mean():.2f}"
else:
    _kpi_avg = "—"

st.markdown(
    f"""
    <div class="kpi-grid">
        <div class="kpi-card kpi-indigo">
            <div class="kpi-icon">📊</div>
            <div class="kpi-label">Rows</div>
            <div class="kpi-value">{_kpi_rows:,}</div>
            <div class="kpi-sub">of {_kpi_total:,} total</div>
        </div>
        <div class="kpi-card kpi-cyan">
            <div class="kpi-icon">🐎</div>
            <div class="kpi-label">Unique horses</div>
            <div class="kpi-value">{_kpi_unique}</div>
            <div class="kpi-sub">in current filter</div>
        </div>
        <div class="kpi-card kpi-pink">
            <div class="kpi-icon">🏆</div>
            <div class="kpi-label">Award categories</div>
            <div class="kpi-value">{_kpi_awards}</div>
            <div class="kpi-sub">distinct categories</div>
        </div>
        <div class="kpi-card kpi-amber">
            <div class="kpi-icon">⚡</div>
            <div class="kpi-label">Avg national points</div>
            <div class="kpi-value">{_kpi_avg}</div>
            <div class="kpi-sub">across filtered rows</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
if "competition_year" in display_df.columns:
    column_config["competition_year"] = st.column_config.NumberColumn(
        "Year", format="%d", width="small"
    )
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
    pts = row.get("nat_points_good", None)
    pts_str = f" · {pts:.2f} pts" if isinstance(pts, (int, float)) and pd.notna(pts) else ""
    st.markdown(
        f"""
        <div class="detail-card">
            <div class="detail-title">✨ {horse}<span style="color:#94a3b8;font-weight:500;">{pts_str}</span></div>
            <div class="detail-sub">Row {row_idx + 1} of {len(display_df):,}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("📋 Row details", expanded=True):
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
