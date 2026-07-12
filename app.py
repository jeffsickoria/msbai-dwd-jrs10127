import os
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import date
from google.cloud import bigquery

from query import get_config, active_trips_table, trips_weather_sql

# Credentials: use GOOGLE_APPLICATION_CREDENTIALS env var if set (local dev),
# otherwise fall back to ADC (Cloud Run attached service account).
_KEY = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if _KEY:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _KEY

st.set_page_config(page_title="Citi Bike Explorer", layout="wide")

# ── Configuration (env-driven; see query.py) ─────────────────────────────────

try:
    CFG = get_config()
except ValueError as exc:
    st.error(f"Configuration error: {exc}")
    st.stop()

TRIPS_TABLE = active_trips_table(CFG)

# ── BigQuery client (one per app process) ────────────────────────────────────

@st.cache_resource
def get_client():
    return bigquery.Client(project=CFG["project"])

# ── Data fetching — one cached daily query per (mode, start, end) ────────────
# The wide result carries all rider series at once, so switching the rider
# radio re-slices the cached frame instead of re-querying BigQuery.

SERIES_COLS = {
    "member": "num_member_trips_nyc",
    "casual": "num_casual_trips_nyc",
}

@st.cache_data(ttl=3600, show_spinner="Querying BigQuery…")
def fetch_daily(mode: str, start: date, end: date) -> pd.DataFrame:
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "DATE", start.isoformat()),
        bigquery.ScalarQueryParameter("e", "DATE", end.isoformat()),
    ])
    return get_client().query(trips_weather_sql(CFG), job_config=cfg).to_dataframe()


def load(rider_type: str, start: date, end: date):
    """Return (wide df, long df of the selected member/casual series).

    The long frame feeds the per-rider-type charts and deliberately contains
    only member/casual — unknown-rider trips are counted in num_nyc_trips
    (and the KPI total) but are never folded into either named series.
    """
    wide = fetch_daily(CFG["source_mode"], start, end)
    types = ["member", "casual"] if rider_type == "both" else [rider_type]
    parts = []
    for rt in types:
        part = wide[["date", SERIES_COLS[rt], "tavg_f", "prcp_inches",
                     "is_weekend", "season", "is_rainy", "is_snowy"]].copy()
        part = part.rename(columns={SERIES_COLS[rt]: "num_trips"})
        part["rider_type"] = rt
        parts.append(part)
    return wide, pd.concat(parts, ignore_index=True)


# ── Sidebar controls ──────────────────────────────────────────────────────────

DATE_MIN = date(2013, 6, 1)
DATE_MAX = date(2026, 5, 31)

st.sidebar.title("Filters")

rider_type = st.sidebar.radio(
    "Rider type",
    options=["member", "casual", "both"],
    index=2,
    horizontal=True,
)

date_range = st.sidebar.slider(
    "Date range",
    min_value=DATE_MIN,
    max_value=DATE_MAX,
    value=(date(2022, 1, 1), date(2024, 12, 31)),
    format="YYYY-MM-DD",
)
start, end = date_range

# ── Load data ─────────────────────────────────────────────────────────────────

wide, df = load(rider_type, start, end)

if df.empty:
    st.warning("No data for selected filters.")
    st.stop()

# ── Header KPIs ───────────────────────────────────────────────────────────────

st.title("Citi Bike NYC — Daily Ridership")

if rider_type == "both":
    # Total NYC trips includes unknown-rider trips, not just member+casual.
    total   = wide["num_nyc_trips"].sum()
    avg_day = wide["num_nyc_trips"].mean()
else:
    total   = df["num_trips"].sum()
    avg_day = df.groupby("date")["num_trips"].sum().mean()
avg_tmp = df["tavg_f"].mean()
days    = df["date"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total trips",      f"{total:,.0f}")
k2.metric("Avg trips / day",  f"{avg_day:,.0f}")
k3.metric("Avg temperature",  f"{avg_tmp:.1f} °F")
k4.metric("Days covered",     f"{days:,}")

# ── Active data source ────────────────────────────────────────────────────────

st.caption(f"Trip data source: `{TRIPS_TABLE}` "
           f"({'verified v2 pipeline' if CFG['source_mode'] == 'v2' else 'course reference (fallback)'})")
if CFG["source_mode"] == "v2":
    st.caption(
        "Data quality: counts independently verified against the official "
        "Citi Bike archive (byte-identical sources; see docs/verification/). "
        "Trips with an unknown rider type (≈0.017%, Oct 2016–Mar 2017 only) are "
        "included in total rides but not in the member/casual series. The "
        "course reference table is known to overcount April 2018 (2×) and "
        "2022 / 2023 / May 2024 (~2.4–3.2%), so totals here can sit below it."
    )

st.divider()

# ── Chart 1: Daily trips + temperature ────────────────────────────────────────

st.subheader("Daily trips & temperature")

COLORS = {"member": "#1f77b4", "casual": "#ff7f0e"}

fig1 = go.Figure()

for rt, grp in df.groupby("rider_type"):
    fig1.add_trace(go.Scatter(
        x=grp["date"], y=grp["num_trips"],
        name=rt.capitalize(), mode="lines",
        line=dict(color=COLORS[rt], width=1.2),
        yaxis="y1",
    ))

# Temperature as thin grey line on secondary axis
tmp = df.drop_duplicates("date").sort_values("date")
fig1.add_trace(go.Scatter(
    x=tmp["date"], y=tmp["tavg_f"],
    name="Avg temp (°F)", mode="lines",
    line=dict(color="#aaa", width=1, dash="dot"),
    yaxis="y2",
))

fig1.update_layout(
    height=360,
    yaxis=dict(title="Trips"),
    yaxis2=dict(title="°F", overlaying="y", side="right", showgrid=False),
    legend=dict(orientation="h", y=1.08),
    margin=dict(l=0, r=0, t=10, b=0),
    hovermode="x unified",
)
st.plotly_chart(fig1, use_container_width=True)

# ── Charts 2 & 3 side-by-side ─────────────────────────────────────────────────

col_a, col_b = st.columns(2)

# Chart 2: Trips vs temperature scatter
with col_a:
    st.subheader("Trips vs temperature")
    scatter_df = df.copy()
    scatter_df["tavg_bucket"] = (scatter_df["tavg_f"] // 5 * 5).astype(int)
    agg = (scatter_df.groupby(["tavg_bucket", "rider_type"])["num_trips"]
           .mean().reset_index())

    fig2 = px.scatter(
        agg, x="tavg_bucket", y="num_trips",
        color="rider_type", color_discrete_map=COLORS,
        trendline="lowess",
        labels={"tavg_bucket": "Avg temp (°F, 5° buckets)",
                "num_trips": "Avg daily trips",
                "rider_type": "Rider type"},
        height=340,
    )
    fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                       legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig2, use_container_width=True)

# Chart 3: Average trips by day of week
with col_b:
    st.subheader("Avg trips by day of week")
    dow_df = df.copy()
    dow_df["dow"] = pd.to_datetime(dow_df["date"]).dt.day_name()
    DOW_ORDER = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    dow_agg = (dow_df.groupby(["dow", "rider_type"])["num_trips"]
               .mean().reset_index())
    dow_agg["dow"] = pd.Categorical(dow_agg["dow"], categories=DOW_ORDER, ordered=True)
    dow_agg = dow_agg.sort_values("dow")

    fig3 = px.bar(
        dow_agg, x="dow", y="num_trips",
        color="rider_type", color_discrete_map=COLORS,
        barmode="group",
        labels={"dow": "", "num_trips": "Avg daily trips", "rider_type": "Rider type"},
        height=340,
    )
    fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                       legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig3, use_container_width=True)

# ── Chart 4: Rain impact ──────────────────────────────────────────────────────

st.subheader("Weather impact on ridership")

impact_df = df.copy()
impact_df["conditions"] = (
    impact_df["is_snowy"].astype(bool).map({True: "Snow"})
    .fillna(impact_df["is_rainy"].astype(bool).map({True: "Rain"}).fillna("Clear"))
)
impact_agg = (impact_df.groupby(["conditions", "rider_type"])["num_trips"]
              .mean().reset_index()
              .sort_values("conditions"))

fig4 = px.bar(
    impact_agg, x="conditions", y="num_trips",
    color="rider_type", color_discrete_map=COLORS,
    barmode="group",
    labels={"conditions": "", "num_trips": "Avg daily trips", "rider_type": "Rider type"},
    category_orders={"conditions": ["Clear", "Rain", "Snow"]},
    height=300,
)
fig4.update_layout(margin=dict(l=0, r=0, t=10, b=0),
                   legend=dict(orientation="h", y=1.08))
st.plotly_chart(fig4, use_container_width=True)

# ── Section 5: Is it us or the weather? ──────────────────────────────────────

st.divider()
st.subheader("Is it us or the weather?")

@st.cache_data(ttl=3600, show_spinner="Loading model residuals…")
def fetch_model(start: date, end: date) -> pd.DataFrame:
    # Model table only covers 2022+; clamp start date silently
    effective_start = max(start, date(2022, 1, 1))
    if effective_start > end:
        return pd.DataFrame()
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "DATE", effective_start.isoformat()),
        bigquery.ScalarQueryParameter("e", "DATE", end.isoformat()),
    ])
    return get_client().query(f"""
        SELECT date, num_nyc_trips, expected_rides, residual, residual_pct
        FROM `{CFG["model_table"]}`
        WHERE date BETWEEN @s AND @e
        ORDER BY date
    """, job_config=cfg).to_dataframe()

mdf = fetch_model(start, end)

if mdf.empty:
    st.info("Model data starts 2022-01-01 — adjust the date range to include 2022 or later.")
else:
    below = mdf[mdf["residual_pct"] < -15]
    above = mdf[mdf["residual_pct"] >  15]

    fig5 = go.Figure()

    # Actual trips
    fig5.add_trace(go.Scatter(
        x=mdf["date"], y=mdf["num_nyc_trips"],
        name="Actual trips", mode="lines",
        line=dict(color="#1f77b4", width=1.5),
    ))

    # Expected trips
    fig5.add_trace(go.Scatter(
        x=mdf["date"], y=mdf["expected_rides"],
        name="Expected (weather + season)", mode="lines",
        line=dict(color="#aaa", width=1.2, dash="dot"),
    ))

    # Red markers: significantly below expected
    fig5.add_trace(go.Scatter(
        x=below["date"], y=below["num_nyc_trips"],
        name="Below expected >15%",
        mode="markers",
        marker=dict(color="red", size=5, symbol="circle"),
        customdata=below[["residual_pct", "expected_rides"]].values,
        hovertemplate="<b>%{x}</b><br>Actual: %{y:,}<br>Expected: %{customdata[1]:,}<br>Δ: %{customdata[0]:.1f}%<extra></extra>",
    ))

    # Green markers: significantly above expected
    fig5.add_trace(go.Scatter(
        x=above["date"], y=above["num_nyc_trips"],
        name="Above expected >15%",
        mode="markers",
        marker=dict(color="green", size=5, symbol="circle"),
        customdata=above[["residual_pct", "expected_rides"]].values,
        hovertemplate="<b>%{x}</b><br>Actual: %{y:,}<br>Expected: %{customdata[1]:,}<br>Δ: %{customdata[0]:.1f}%<extra></extra>",
    ))

    fig5.update_layout(
        height=400,
        yaxis=dict(title="Trips"),
        legend=dict(orientation="h", y=1.08),
        margin=dict(l=0, r=0, t=10, b=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig5, use_container_width=True)

    pct_red   = len(below) / len(mdf) * 100
    pct_green = len(above) / len(mdf) * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("Days below expected >15%", f"{len(below):,}",  f"{pct_red:.1f}% of days",   delta_color="inverse")
    c2.metric("Days above expected >15%", f"{len(above):,}",  f"{pct_green:.1f}% of days", delta_color="normal")
    c3.metric("Days within ±15%",         f"{len(mdf) - len(below) - len(above):,}",
              f"{100 - pct_red - pct_green:.1f}% of days", delta_color="off")

    st.caption(
        "Days in red ran significantly below what weather and season alone would predict — "
        "likely operational, external, or event-driven causes. The model was fitted on the "
        "pre-v2 daily series; its actuals may sit slightly above the verified v2 counts."
    )
