import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

import folium
from streamlit_folium import st_folium

# ---------------------------------------------------------
# KONFIGURÁCIÓ
# ---------------------------------------------------------
BASE_INDEX_URL = "https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/"

# ---------------------------------------------------------
# SEGÉDFÜGGVÉNYEK
# ---------------------------------------------------------
def build_filename_for_date(date_obj):
    return f"HABP_1D_{date_obj.strftime('%Y%m%d')}.csv.zip"


def download_zip_bytes(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def extract_csv_from_zipbytes(zip_bytes, expected_csv_name):
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    with z.open(expected_csv_name) as f:
        return f.read().decode("utf-8", errors="replace")


def to_float_clean(series):
    return pd.to_numeric(
        series.astype(str)
        .str.strip()
        .replace({"-999": None, "": None})
        .str.replace(",", ".", regex=False),
        errors="coerce",
    )


def parse_data(csv_text):
    df = pd.read_csv(io.StringIO(csv_text), sep=";", dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Állomásadatok
    df["station_number"] = df.iloc[:, 1]
    df["station_name"] = df.iloc[:, 2]
    df["station_full"] = df["station_name"] + " (" + df["station_number"] + ")"

    # Hőmérséklet adatok
    df["min_val"] = to_float_clean(df.iloc[:, 10])
    df["max_val"] = to_float_clean(df.iloc[:, 12])

    # Koordináták
    lat_col = next((c for c in df.columns if c.lower() in ["lat", "latitude"]), None)
    lon_col = next((c for c in df.columns if c.lower() in ["lon", "longitude"]), None)

    if lat_col and lon_col:
        df["lat"] = pd.to_numeric(
            df[lat_col].str.replace(",", ".", regex=False), errors="coerce"
        )
        df["lon"] = pd.to_numeric(
            df[lon_col].str.replace(",", ".", regex=False), errors="coerce"
        )
    else:
        df["lat"] = None
        df["lon"] = None

    def extreme(df_, col, fn):
        s = df_[col].dropna()
        if s.empty:
            return None
        idx = getattr(s, fn)()
        return {
            "value": float(df_.loc[idx, col]),
            "station": df_.loc[idx, "station_full"],
            "lat": df_.loc[idx, "lat"],
            "lon": df_.loc[idx, "lon"],
        }

    # Országos szélsők
    min_res = extreme(df, "min_val", "idxmin")
    max_res = extreme(df, "max_val", "idxmax")

    # Budapest szűrés
    df_bp = df[df["station_name"].str.contains("Budapest", case=False, na=False)].copy()
    bp_min = extreme(df_bp, "min_val", "idxmin")
    bp_max = extreme(df_bp, "max_val", "idxmax")

    return df, df_bp, min_res, max_res, bp_min, bp_max


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------
for key in ["loaded", "df", "df_bp", "min_res", "max_res", "bp_min", "bp_max"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Napi hőmérsékleti szélsőértékek",
    layout="centered",
)

st.title("🌡️ Napi hőmérsékleti szélsőértékek")
st.caption("Forrás: HungaroMet – napi szinoptikus jelentések")

date_selected = st.date_input(
    "📅 Dátum",
    value=datetime.now(ZoneInfo("Europe/Budapest")).date() - timedelta(days=1),
)

if st.button("📥 Adatok betöltése"):
    try:
        fname = build_filename_for_date(date_selected)
        zip_bytes = download_zip_bytes(BASE_INDEX_URL + fname)
        csv_text = extract_csv_from_zipbytes(zip_bytes, fname.replace(".zip", ""))

        (
            st.session_state.df,
            st.session_state.df_bp,
            st.session_state.min_res,
            st.session_state.max_res,
            st.session_state.bp_min,
            st.session_state.bp_max,
        ) = parse_data(csv_text)

        st.session_state.loaded = True

    except Exception as e:
        st.error(f"Hiba történt: {e}")

# ---------------------------------------------------------
# MEGJELENÍTÉS
# ---------------------------------------------------------
if st.session_state.loaded:

    st.subheader("🇭🇺 Országos szélsők")
    c1, c2 = st.columns(2)

    c1.metric(
        "🔥 Maximum",
        f"{st.session_state.max_res['value']} °C",
        st.session_state.max_res["station"],
    )

    c2.metric(
        "❄️ Minimum",
        f"{st.session_state.min_res['value']} °C",
        st.session_state.min_res["station"],
    )

    st.subheader("🏙️ Budapest szélsők")
    c1, c2 = st.columns(2)

    if st.session_state.bp_max:
        c1.metric(
            "🔥 BP maximum",
            f"{st.session_state.bp_max['value']} °C",
            st.session_state.bp_max["station"],
        )

    if st.session_state.bp_min:
        c2.metric(
            "❄️ BP minimum",
            f"{st.session_state.bp_min['value']} °C",
            st.session_state.bp_min["station"],
        )

    st.subheader("📋 Budapesti mérőállomások")
    st.dataframe(
        st.session_state.df_bp[
            ["station_name", "station_number", "min_val", "max_val"]
        ]
        .rename(
            columns={
                "station_name": "Állomás",
                "station_number": "Kód",
                "min_val": "Minimum (°C)",
                "max_val": "Maximum (°C)",
            }
        )
        .sort_values("Állomás"),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("🗺️ Országos térkép")
    m = folium.Map(location=[47.1, 19.5], zoom_start=7)
    for _, r in st.session_state.df.dropna(subset=["lat", "lon"]).iterrows():
        folium.CircleMarker(
            [r.lat, r.lon],
            radius=4,
            color="black",
            fill=True,
            fill_opacity=0.9,
            tooltip=r.station_full,
        ).add_to(m)
    st_folium(m, width=750, height=500)

    st.subheader("🗺️ Budapest térkép")
    m_bp = folium.Map(location=[47.4979, 19.0402], zoom_start=11)
    for _, r in st.session_state.df_bp.dropna(subset=["lat", "lon"]).iterrows():
        folium.CircleMarker(
            [r.lat, r.lon],
            radius=7,
            color="black",
            fill=True,
            fill_opacity=0.9,
            tooltip=r.station_full,
        ).add_to(m_bp)
    st_folium(m_bp, width=750, height=500)
