import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------
# KONFIG
# ---------------------------------------------------------
BASE_INDEX_URL = "https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/"

CITY_BACKGROUNDS = {
    "Országos": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Flag_of_Hungary.svg/1280px-Flag_of_Hungary.svg.png",
    "Budapest": "https://images.unsplash.com/photo-1549640376-8cc6b7c2f42f",
    "Debrecen": "https://images.unsplash.com/photo-1618828665087-0cfdc2c8e3b2",
    "Győr": "https://images.unsplash.com/photo-1604152135912-04a022e236a3",
    "Miskolc": "https://images.unsplash.com/photo-1616431684203-3a7a5d2c2c0f",
    "Pécs": "https://images.unsplash.com/photo-1600353068793-65d7dcddcb3c",
    "Szeged": "https://images.unsplash.com/photo-1594737625785-4a4e6b2e8b45",
}

CITIES = ["Budapest", "Debrecen", "Győr", "Miskolc", "Pécs", "Szeged"]

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
    df["station_number"] = df.iloc[:, 1]
    df["station_name"] = df.iloc[:, 2]
    df["min_val"] = to_float_clean(df.iloc[:, 10])
    df["max_val"] = to_float_clean(df.iloc[:, 12])
    return df


def calc_extremes(df):
    return {"min": df["min_val"].min(), "max": df["max_val"].max()}


def city_card(title, ext):
    bg = CITY_BACKGROUNDS.get(title, "")
    max_v = f"{ext['max']:.1f} °C" if pd.notna(ext["max"]) else "–"
    min_v = f"{ext['min']:.1f} °C" if pd.notna(ext["min"]) else "–"

    st.markdown(
        f"""
        <div style="
            position:relative;
            padding:14px;
            border-radius:14px;
            background:#ffffff;
            box-shadow:0 4px 10px rgba(0,0,0,0.08);
            overflow:hidden;
        ">
            <div style="
                position:absolute;
                inset:0;
                background-image:url('{bg}');
                background-size:cover;
                background-position:center;
                opacity:0.10;
            "></div>

            <div style="position:relative;">
                <div style="font-size:1.3em;font-weight:700;margin-bottom:6px;">
                    {title}
                </div>
                <div style="color:#d62728;font-size:1.05em;">🔥 Max: {max_v}</div>
                <div style="color:#1f77b4;font-size:1.05em;">❄️ Min: {min_v}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(page_title="Napi hőmérsékleti riport")

st.title("🌡️ Napi hőmérsékleti riport")
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
        df = parse_data(csv_text)

        st.session_state["zip_bytes"] = zip_bytes
        st.session_state["zip_name"] = fname

        # ------------------ ÖSSZEFOGLALÓ ------------------
        st.subheader("📊 Összefoglaló")

        cols = st.columns(3)
        with cols[0]:
            city_card("Országos", calc_extremes(df))

        for i, city in enumerate(CITIES):
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)]
            with cols[(i + 1) % 3]:
                city_card(city, calc_extremes(df_city))

        st.divider()

        # ------------------ LETÖLTÉSEK ------------------
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "📦 Eredeti ZIP",
                st.session_state["zip_bytes"],
                st.session_state["zip_name"],
                mime="application/zip",
            )

        with d2:
            export_df = pd.DataFrame([[
                date_selected.strftime("%Y-%m-%d"),
                calc_extremes(df)["max"],
                calc_extremes(df)["min"],
            ]], columns=["Dátum", "Országos max", "Országos min"])

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                export_df.to_excel(w, index=False)

            st.download_button(
                "📊 Excel export",
                buf.getvalue(),
                f"napi_homerseklet_{date_selected}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"Hiba történt: {e}")
