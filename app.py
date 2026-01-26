
Gárdonyi András <andras.gardonyi@gmail.com>
10:10 (1 perccel ezelőtt)
címzett: én

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

def extract_csv_from_zipbytes(zip_bytes, expected_csv_name=None):
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    if expected_csv_name and expected_csv_name in z.namelist():
        with z.open(expected_csv_name) as f:
            return f.read().decode("utf-8", errors="replace")
    for name in z.namelist():
        if name.lower().endswith(".csv"):
            with z.open(name) as f:
                return f.read().decode("utf-8", errors="replace")
    raise FileNotFoundError("CSV fájl nem található a ZIP-ben")

def parse_and_find_extremes(csv_text):
    df = pd.read_csv(io.StringIO(csv_text), sep=";", dtype=str)
    df.columns = [c.strip() for c in df.columns]

    df["station_number"] = df.iloc[:, 1].str.strip()
    df["station_name"] = df.iloc[:, 2].str.strip()
    df["station_full"] = df["station_name"] + " (" + df["station_number"] + ")"

    min_col = df.columns[10]
    max_col = df.columns[12]

    def to_float(col):
        return (
            col.str.replace(",", ".", regex=False)
               .replace({"-999": None, "": None})
               .astype(float)
        )

    df["min_val"] = to_float(df[min_col])
    df["max_val"] = to_float(df[max_col])

    lat_col = next((c for c in df.columns if c.lower() in ["lat", "latitude"]), None)
    lon_col = next((c for c in df.columns if c.lower() in ["lon", "longitude"]), None)

    if lat_col and lon_col:
        df["lat"] = pd.to_numeric(df[lat_col].str.replace(",", "."), errors="coerce")
        df["lon"] = pd.to_numeric(df[lon_col].str.replace(",", "."), errors="coerce")
    else:
        df["lat"] = None
        df["lon"] = None

    def extreme(df_, col, func):
        if df_[col].dropna().empty:
            return None
        idx = getattr(df_[col], func)()
        return {
            "value": float(df_.loc[idx, col]),
            "station": df_.loc[idx, "station_full"],
            "lat": df_.loc[idx, "lat"],
            "lon": df_.loc[idx, "lon"],
        }

    min_res = extreme(df, "min_val", "idxmin")
    max_res = extreme(df, "max_val", "idxmax")

    # Budapest szűrés
    df_bp = df[df["station_name"].str.contains("Budapest", case=False, na=False)].copy()
    bp_min_res = extreme(df_bp, "min_val", "idxmin")
    bp_max_res = extreme(df_bp, "max_val", "idxmax")

    return min_res, max_res, df, bp_min_res, bp_max_res, df_bp

# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.set_page_config(page_title="Napi hőmérsékleti szélsők", layout="centered")

st.title("🌡️ Napi hőmérsékleti szélsőértékek – Magyarország")
st.caption("Forrás: HungaroMet – szinoptikus napi jelentések")

date_selected = st.date_input(
    "📅 Dátum kiválasztása",
    value=datetime.now(ZoneInfo("Europe/Budapest")).date() - timedelta(days=1),
)

if st.button("📥 Adatok betöltése"):
    try:
        fname = build_filename_for_date(date_selected)
        zip_bytes = download_zip_bytes(BASE_INDEX_URL + fname)
        csv_text = extract_csv_from_zipbytes(zip_bytes, fname.replace(".zip", ""))

        (
            min_res,
            max_res,
            df_all,
            bp_min_res,
            bp_max_res,
            df_bp,
        ) = parse_and_find_extremes(csv_text)

        st.success("✔ Adatok sikeresen betöltve")

        # ---------------------------------
        # Országos szélsők
        # ---------------------------------
        st.subheader("🇭🇺 Országos szélsőértékek")
        c1, c2 = st.columns(2)
        c1.metric("🔥 Maximum", f"{max_res['value']} °C", max_res["station"])
        c2.metric("❄️ Minimum", f"{min_res['value']} °C", min_res["station"])

        # ---------------------------------
        # Budapest szélsők
        # ---------------------------------
        st.subheader("🏙️ Budapest szélsőértékek")
        c1, c2 = st.columns(2)
        if bp_max_res:
            c1.metric("🔥 BP max", f"{bp_max_res['value']} °C", bp_max_res["station"])
        if bp_min_res:
            c2.metric("❄️ BP min", f"{bp_min_res['value']} °C", bp_min_res["station"])

        # ---------------------------------
        # Budapest állomások táblázat
        # ---------------------------------
        st.subheader("📋 Budapesti mérőállomások")
        st.dataframe(
            df_bp[
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

        # ---------------------------------
        # Országos térkép
        # ---------------------------------
        st.subheader("🗺️ Országos térkép")
        m = folium.Map(location=[47.1, 19.5], zoom_start=7)
        for _, r in df_all.dropna(subset=["lat", "lon"]).iterrows():
            folium.CircleMarker(
                [r.lat, r.lon], radius=4, color="black", fill=True
            ).add_to(m)
        st_folium(m, width=750, height=500)

        # ---------------------------------
        # Budapest térkép
        # ---------------------------------
        st.subheader("🗺️ Budapest térkép")
        m_bp = folium.Map(location=[47.4979, 19.0402], zoom_start=11)
        for _, r in df_bp.dropna(subset=["lat", "lon"]).iterrows():
            folium.CircleMarker(
                [r.lat, r.lon],
                radius=7,
                color="black",
                fill=True,
                tooltip=r.station_full,
            ).add_to(m_bp)
        st_folium(m_bp, width=750, height=500)

    except Exception as e:
        st.error(f"Hiba történt: {e}")
