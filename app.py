import os
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import date
from google.cloud import bigquery

# Credentials: use GOOGLE_APPLICATION_CREDENTIALS env var if set (local dev),
# otherwise fall back to ADC (Cloud Run attached service account).
_KEY = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if _KEY:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _KEY

st.set_page_config(page_title="Citi Bike Explorer", layout="wide")

# ── BigQuery client (one per app process) ────────────────────────────────────

@st.cache_resource
def get_client():
    return bigquery.Client(project="msbai-dwd-jrs10127")

# ── Data fetching — cached per (rider_type, start, end) ──────────────────────
# Each unique arg combination is cached independently, so changing rider_type
# reuses the cached other type rather than re-querying it.

TRIP_COLS = {
    "member": "num_member_trips_nyc",
    "casual": "num_casual_trips_nyc",
}

@st.cache_data(ttl=3600, show_spinner="Querying BigQuery…")
def fetch(rider_type: str, start: date, end: date) -> pd.DataFrame:
    col = TRIP_COLS[rider_type]
    sql = f"""
        SELECT
            t.date,
            t.{col}                                         AS num_trips,
            w.tavg_f,
            w.prcp_inches,
            w.is_weekend,
            w.season,
            w.is_rainy,
            w.is_snowy
        FROM `nyu-datasets.citibike.m_daily_trips`      t
        JOIN `nyu-datasets.weather.m_weather_daily_nyc` w USING (date)
        WHERE t.date BETWEEN @s AND @e
        ORDER BY t.date
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "DATE", start.isoformat()),
        bigquery.ScalarQueryParameter("e", "DATE", end.isoformat()),
    ])
    df = get_client().query(sql, job_config=cfg).to_dataframe()
    df["rider_type"] = rider_type
    return df


def load(rider_type: str, start: date, end: date) -> pd.DataFrame:
    """Return combined df for 'member', 'casual', or 'both'."""
    if rider_type == "both":
        return pd.concat([fetch("member", start, end), fetch("casual", start, end)],
                         ignore_index=True)
    return fetch(rider_type, start, end)


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

df = load(rider_type, start, end)

if df.empty:
    st.warning("No data for selected filters.")
    st.stop()

# ── Header KPIs ───────────────────────────────────────────────────────────────

st.title("Citi Bike NYC — Daily Ridership")

total   = df["num_trips"].sum()
avg_day = df.groupby("date")["num_trips"].sum().mean()
avg_tmp = df["tavg_f"].mean()
days    = df["date"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total trips",      f"{total:,.0f}")
k2.metric("Avg trips / day",  f"{avg_day:,.0f}")
k3.metric("Avg temperature",  f"{avg_tmp:.1f} °F")
k4.metric("Days covered",     f"{days:,}")

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
    return get_client().query("""
        SELECT date, num_nyc_trips, expected_rides, residual, residual_pct
        FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`
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
        "likely operational, external, or event-driven causes."
    )
