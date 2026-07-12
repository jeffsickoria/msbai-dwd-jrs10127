import os
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import date
from google.cloud import bigquery

from query import (get_config, active_trips_table, trips_weather_sql,
                   detect_model_kind, model_sql)

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

# Data-derived finding: warm days vs cold days (per-date total across shown series)
_daily_tot = df.groupby("date")["num_trips"].sum()
_tmp_by_date = df.drop_duplicates("date").set_index("date")["tavg_f"]
_warm = _daily_tot[_tmp_by_date >= _tmp_by_date.quantile(0.75)].mean()
_cold = _daily_tot[_tmp_by_date <= _tmp_by_date.quantile(0.25)].mean()
if _cold and _warm:
    _mult = _warm / _cold
    st.caption(
        f"**Finding:** the warmest quarter of days averages **{_warm:,.0f}** trips/day "
        f"versus **{_cold:,.0f}** on the coldest quarter — about **{_mult:.1f}× more** "
        f"riding when it's warm.")

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

    # Finding: locate the temperature bucket with peak average ridership
    _bucket_tot = (scatter_df.groupby("tavg_bucket")["num_trips"].mean())
    if len(_bucket_tot):
        _peak_b = int(_bucket_tot.idxmax()); _peak_v = _bucket_tot.max()
        _cold_v = _bucket_tot.loc[_bucket_tot.index.min()]
        _updown = "then eases off in extreme heat" if _peak_b < int(_bucket_tot.index.max()) else "and keeps rising"
        st.caption(
            f"**Finding:** average ridership peaks near **{_peak_b}–{_peak_b+5}°F** "
            f"(~{_peak_v:,.0f} trips/day, ~{_peak_v/_cold_v:.1f}× the coldest buckets) {_updown}.")

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

    # Finding: weekday vs weekend split, per shown rider type
    _wk = dow_df.copy()
    _wk["is_wknd"] = pd.to_datetime(_wk["date"]).dt.dayofweek >= 5
    _bits = []
    for rt in sorted(_wk["rider_type"].unique()):
        g = _wk[_wk["rider_type"] == rt].groupby("is_wknd")["num_trips"].mean()
        if True in g.index and False in g.index and g[False]:
            pct = (g[True] - g[False]) / g[False] * 100
            _bits.append(f"{rt} ride **{abs(pct):.0f}% {'more' if pct>0 else 'fewer'}** on weekends")
    if _bits:
        st.caption("**Finding:** " + "; ".join(_bits) + " than on weekdays.")

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

# Finding: rain/snow suppression vs clear, on per-date totals
_cond = impact_df.groupby(["date", "conditions"])["num_trips"].sum().reset_index()
_cm = _cond.groupby("conditions")["num_trips"].mean()
if "Clear" in _cm.index and _cm.get("Clear"):
    _parts = []
    for c in ("Rain", "Snow"):
        if c in _cm.index:
            d = (_cm[c] - _cm["Clear"]) / _cm["Clear"] * 100
            _parts.append(f"**{abs(d):.0f}% {'fewer' if d<0 else 'more'}** on {c.lower()}y days")
    if _parts:
        st.caption("**Finding:** average daily trips run " + " and ".join(_parts)
                   + f" versus clear days (~{_cm['Clear']:,.0f}/day).")

# ── Section 5: Is it us or the weather? ──────────────────────────────────────

st.divider()
st.subheader("Is it us or the weather?")

# Detect which model table is wired in (v1 legacy vs v2 weather-adjusted).
# A missing/incompatible table raises -> we show a clear error, never stale data.
try:
    MODEL_KIND = detect_model_kind(get_client(), CFG)
    MODEL_ERROR = None
except ValueError as exc:
    MODEL_KIND, MODEL_ERROR = None, str(exc)


@st.cache_data(ttl=3600, show_spinner="Loading model…")
def fetch_model(kind: str, start: date, end: date) -> pd.DataFrame:
    effective_start = max(start, date(2022, 1, 1))  # model window starts 2022
    if effective_start > end:
        return pd.DataFrame()
    job = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "DATE", effective_start.isoformat()),
        bigquery.ScalarQueryParameter("e", "DATE", end.isoformat()),
    ])
    return get_client().query(model_sql(kind, CFG), job_config=job).to_dataframe()


if MODEL_ERROR:
    st.error(f"Model section unavailable: {MODEL_ERROR}. "
             f"Set MODEL_TABLE to a compatible model table (v1 or v2).")
else:
    mdf = fetch_model(MODEL_KIND, start, end)
    # v2 carries total/member/casual; show the selected rider series (total for 'both').
    if MODEL_KIND == "v2":
        want = "total" if rider_type == "both" else rider_type
        mdf = mdf[mdf["rider_series"] == want].copy()
    if mdf.empty:
        st.info("Model data starts 2022-01-01 — widen the date range to include 2022 or later.")
    else:
        has_band = mdf["lower_expected_bound"].notna().any()
        flagged = mdf[mdf["gap_flag"]]
        below = flagged[flagged["percent_gap"] < 0]
        above = flagged[flagged["percent_gap"] > 0]

        fig5 = go.Figure()
        # Expected range band (v2 only)
        if has_band:
            fig5.add_trace(go.Scatter(
                x=mdf["date"], y=mdf["upper_expected_bound"], mode="lines",
                line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig5.add_trace(go.Scatter(
                x=mdf["date"], y=mdf["lower_expected_bound"], mode="lines",
                line=dict(width=0), fill="tonexty", fillcolor="rgba(150,150,150,0.25)",
                name="Expected range (~95%)", hoverinfo="skip"))
        fig5.add_trace(go.Scatter(
            x=mdf["date"], y=mdf["actual_trips"], name="Actual trips",
            mode="lines", line=dict(color="#1f77b4", width=1.5)))
        fig5.add_trace(go.Scatter(
            x=mdf["date"], y=mdf["expected_trips"], name="Expected (weather + calendar)",
            mode="lines", line=dict(color="#888", width=1.2, dash="dot")))
        fig5.add_trace(go.Scatter(
            x=below["date"], y=below["actual_trips"], name="Unusually low", mode="markers",
            marker=dict(color="red", size=6),
            customdata=below[["percent_gap", "expected_trips"]].values,
            hovertemplate="<b>%{x}</b><br>Actual: %{y:,}<br>Expected: %{customdata[1]:,.0f}<br>Gap: %{customdata[0]:.1f}%<extra></extra>"))
        fig5.add_trace(go.Scatter(
            x=above["date"], y=above["actual_trips"], name="Unusually high", mode="markers",
            marker=dict(color="green", size=6),
            customdata=above[["percent_gap", "expected_trips"]].values,
            hovertemplate="<b>%{x}</b><br>Actual: %{y:,}<br>Expected: %{customdata[1]:,.0f}<br>Gap: %{customdata[0]:.1f}%<extra></extra>"))
        fig5.update_layout(height=400, yaxis=dict(title="Trips"),
                           legend=dict(orientation="h", y=1.08),
                           margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
        st.plotly_chart(fig5, use_container_width=True)

        n = len(mdf)
        c1, c2, c3 = st.columns(3)
        c1.metric("Unusually low days", f"{len(below):,}", f"{len(below)/n*100:.1f}% of days", delta_color="inverse")
        c2.metric("Unusually high days", f"{len(above):,}", f"{len(above)/n*100:.1f}% of days", delta_color="normal")
        c3.metric("Within expected range", f"{n - len(flagged):,}", f"{(n-len(flagged))/n*100:.1f}% of days", delta_color="off")

        # Dynamic one-sentence finding with direction + magnitude
        series_label = ("total" if MODEL_KIND != "v2" or rider_type == "both" else rider_type)
        if len(flagged):
            worst = flagged.loc[flagged["percent_gap"].abs().idxmax()]
            wd = worst["date"]
            wd = wd.date() if hasattr(wd, "date") else wd
            st.caption(
                f"**Finding:** over this range, **{series_label}** ridership fell outside the model's "
                f"expected range on **{len(flagged)} of {n} days** ({len(flagged)/n*100:.0f}%); the "
                f"largest gap was **{wd}**, ~**{abs(worst['percent_gap']):.0f}% "
                f"{'below' if worst['percent_gap']<0 else 'above'}** expected.")
        else:
            st.caption(f"**Finding:** **{series_label}** ridership stayed within the model's expected "
                       f"range on all {n} days shown.")

        st.caption(
            "Flagged days are **outside the model's typical error range and merit investigation** — "
            "they do **not** prove a bike shortage, outage, event, or promotion; the model describes "
            "weather/calendar expectations and establishes no cause."
            + ("" if MODEL_KIND == "v2" else
               " ⚠️ This is the pre-v2 model (fitted on the reference-era series; its 2022+ actuals "
               "run ~3% above the verified v2 counts). The refitted v2 model supersedes it once "
               "MODEL_TABLE points to trips_daily_model_v2."))
