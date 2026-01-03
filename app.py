import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# =========================
# OLDAL BEÁLLÍTÁS
# =========================
st.set_page_config(
    page_title="Magyarországi Súlyozott Hőmérséklet",
    layout="wide"
)

st.title("🌡️ Súlyozott országos hőmérsékleti szélsőértékek")

# =========================
# MAGYARORSZÁG POLIGON
# =========================
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95),
    (17.50, 48.05), (18.50, 48.10), (19.05, 48.30), (19.80, 48.60),
    (20.90, 48.55), (22.15, 48.40), (22.85, 48.35), (22.95, 47.90),
    (22.60, 47.45), (21.75, 46.85), (21.40, 46.25), (20.50, 46.10),
    (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25),
    (16.11, 46.60)
]

HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# =========================
# REFERENCIA VÁROSOK
# =========================
CITIES = [
    {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23},
    {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78},
]

def nearest_city(lat, lon):
    d = [
        ((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"])
        for c in CITIES
    ]
    return min(d)[1]

# =========================
# MODELLEK ÉS SÚLYOK
# =========================
MODELS = {
    "ecmwf_ifs": 0.45,
    "gfs_seamless": 0.30,
    "icon_seamless": 0.25
}

# =========================
# RÁCSPONT GENERÁLÁS
# =========================
def generate_grid():
    lats = np.arange(45.8, 48.6, 0.25)
    lons = np.arange(16.2, 22.8, 0.35)

    points = []
    for lat in lats:
        for lon in lons:
            if HU_POLY.contains(Point(lon, lat)):
                points.append((lat, lon))

    return points

GRID_POINTS = generate_grid()

# =========================
# ADATLEKÉRÉS
# =========================
@st.cache_data(ttl=3600)
def fetch_weighted_data(target_date):
    start = (target_date - timedelta(days=1)).strftime("%Y-%m-%dT18:00")
    end = target_date.strftime("%Y-%m-%dT18:00")

    rows = []

    for lat, lon in GRID_POINTS:
        w_min, w_max = 0.0, 0.0

        for model, weight in MODELS.items():
            try:
                r = requests.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "hourly": "temperature_2m",
                        "models": model,
                        "start_hour": start,
                        "end_hour": end,
                        "timezone": "UTC"
                    },
                    timeout=10
                ).json()

                temps = r["hourly"]["temperature_2m"]
                w_min += min(temps) * weight
                w_max += max(temps) * weight

            except Exception:
                continue

        rows.append({
            "lat": lat,
            "lon": lon,
            "min": w_min,
            "max": w_max
        })

    return pd.DataFrame(rows)

# =========================
# SIDEBAR
# =========================
if st.sidebar.button("🔄 Cache törlése"):
    st.cache_data.clear()
    st.rerun()

target_date = st.sidebar.date_input(
    "Előrejelzési nap",
    datetime.utcnow().date() + timedelta(days=1)
)

# =========================
# FUTTATÁS
# =========================
with st.spinner("Adatok lekérése..."):
    df = fetch_weighted_data(target_date)

if df.empty:
    st.error("Nem érkezett adat.")
    st.stop()

# =========================
# ORSZÁGOS SZÉLSŐÉRTÉKEK
# =========================
min_row = df.loc[df["min"].idxmin()]
max_row = df.loc[df["max"].idxmax()]

c1, c2 = st.columns(2)
c1.metric(
    "🌡️ Országos minimum",
    f"{min_row['min']:.1f} °C",
    nearest_city(min_row["lat"], min_row["lon"])
)
c2.metric(
    "🔥 Országos maximum",
    f"{max_row['max']:.1f} °C",
    nearest_city(max_row["lat"], max_row["lon"])
)

st.divider()

# =========================
# TÉRKÉP
# =========================
def draw_map(df, column, title, colorscale):
    fig = px.scatter_mapbox(
        df,
        lat="lat",
        lon="lon",
        color=column,
        color_continuous_scale=colorscale,
        zoom=6.1,
        center={"lat": 47.15, "lon": 19.5},
        mapbox_style="carto-positron"
    )

    fig.add_trace(go.Scattermapbox(
        lat=HU_LINE_LATS,
        lon=HU_LINE_LONS,
        mode="lines",
        line=dict(width=3, color="black"),
        showlegend=False
    ))

    fig.update_traces(marker=dict(size=16, opacity=0.9))
    fig.update_layout(title=title, margin=dict(l=0, r=0, t=40, b=0))
    return fig

m1, m2 = st.columns(2)
m1.plotly_chart(draw_map(df, "min", "Súlyozott minimum", "Viridis"), use_container_width=True)
m2.plotly_chart(draw_map(df, "max", "Súlyozott maximum", "Reds"), use_container_width=True)
