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

CITIES = [
    "Budapest",
    "Debrecen",
    "Győr",
    "Miskolc",
    "Pécs",
    "Szeged",
]

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
    df["station_full"] = df["station_name"] + " (" + df["station_number"] + ")"

    df["min_val"] = to_float_clean(df.iloc[:, 10])
    df["max_val"] = to_float_clean(df.iloc[:, 12])

    return df


def calc_extremes(df):
    res = {}
    if df["min_val"].dropna().empty:
        res["min"] = None
    else:
        idx = df["min_val"].idxmin()
        res["min"] = (df.loc[idx, "min_val"], df.loc[idx, "station_full"])

    if df["max_val"].dropna().empty:
        res["max"] = None
    else:
        idx = df["max_val"].idxmax()
        res["max"] = (df.loc[idx, "max_val"], df.loc[idx, "station_full"])

    return res


def highlight_extremes(df):
    min_val = df["min_val"].min()
    max_val = df["max_val"].max()

    def style(row):
        styles = []
        for col in row.index:
            if col == "Minimum (°C)" and row[col] == min_val:
                styles.append("color: blue; font-weight: bold;")
            elif col == "Maximum (°C)" and row[col] == max_val:
                styles.append("color: red; font-weight: bold;")
            else:
                styles.append("")
        return styles

    return style


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(page_title="Városi hőmérsékleti szélsők", layout="centered")

st.title("🌡️ Városi hőmérsékleti minimum és maximum értékek")
st.caption("Forrás: HungaroMet – napi szinoptikus jelentések")

date_selected = st.date_input(
    "📅 Dátum kiválasztása",
    value=datetime.now(ZoneInfo("Europe/Budapest")).date() - timedelta(days=1),
)

if st.button("📥 Adatok betöltése"):
    try:
        fname = build_filename_for_date(date_selected)
        zip_bytes = download_zip_bytes(BASE_INDEX_URL + fname)
        csv_text = extract_csv_from_zipbytes(zip_bytes, fname.replace(".zip", ""))

        df = parse_data(csv_text)

        st.success("✔ Adatok betöltve")

        # ---------------------------------------------
        # ORSZÁGOS SZÉLSŐK
        # ---------------------------------------------
        st.subheader("🇭🇺 Országos hőmérsékleti szélsők")

        extremes = calc_extremes(df)

        c1, c2 = st.columns(2)
        if extremes["max"]:
            c1.metric("🔥 Maximum", f"{extremes['max'][0]} °C", extremes["max"][1])
        if extremes["min"]:
            c2.metric("❄️ Minimum", f"{extremes['min'][0]} °C", extremes["min"][1])

        st.divider()

        # ---------------------------------------------
        # VÁROSOK
        # ---------------------------------------------
        for city in CITIES:
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)].copy()

            if df_city.empty:
                continue

            st.subheader(f"🏙️ {city}")

            city_ext = calc_extremes(df_city)

            c1, c2 = st.columns(2)
            if city_ext["max"]:
                c1.metric("🔥 Maximum", f"{city_ext['max'][0]} °C", city_ext["max"][1])
            if city_ext["min"]:
                c2.metric("❄️ Minimum", f"{city_ext['min'][0]} °C", city_ext["min"][1])

            table_df = (
                df_city[
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
                .sort_values("Állomás")
            )

            st.dataframe(
                table_df.style.apply(highlight_extremes(table_df), axis=1),
                use_container_width=True,
                hide_index=True,
            )

            st.divider()

    except Exception as e:
        st.error(f"Hiba történt: {e}")
