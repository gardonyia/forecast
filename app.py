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

    df["min_val"] = to_float_clean(df.iloc[:, 10])
    df["max_val"] = to_float_clean(df.iloc[:, 12])

    return df


def calc_extremes(df):
    return {
        "min": df["min_val"].min(),
        "max": df["max_val"].max(),
    }


def prepare_table(df_city):
    return (
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


def format_for_display(df):
    df_disp = df.copy()
    for col in ["Minimum (°C)", "Maximum (°C)"]:
        df_disp[col] = df_disp[col].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else "Nincs adat"
        )
    return df_disp


def style_extremes(df_numeric):
    min_v = df_numeric["Minimum (°C)"].min()
    max_v = df_numeric["Maximum (°C)"].max()

    def style(row):
        return [
            "color: blue; font-weight: bold"
            if col == "Minimum (°C)" and row[col] == min_v
            else "color: red; font-weight: bold"
            if col == "Maximum (°C)" and row[col] == max_v
            else ""
            for col in row.index
        ]

    return style


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(page_title="Napi hőmérsékleti riport", layout="wide")

st.title("🌡️ Napi hőmérsékleti riport")
st.caption("Forrás: HungaroMet – napi szinoptikus jelentések")

top_col1, top_col2 = st.columns([1, 3])

with top_col1:
    date_selected = st.date_input(
        "📅 Dátum",
        value=datetime.now(ZoneInfo("Europe/Budapest")).date() - timedelta(days=1),
    )
    load_btn = st.button("📥 Adatok betöltése")

if load_btn:
    try:
        fname = build_filename_for_date(date_selected)
        zip_bytes = download_zip_bytes(BASE_INDEX_URL + fname)
        csv_text = extract_csv_from_zipbytes(zip_bytes, fname.replace(".zip", ""))

        df = parse_data(csv_text)

        st.session_state["zip_bytes"] = zip_bytes
        st.session_state["zip_name"] = fname

        # -------------------------------------------------
        # DASHBOARD METRICÁK
        # -------------------------------------------------
        st.subheader("📊 Összefoglaló")

        metric_cols = st.columns(7)
        hu = calc_extremes(df)
        metric_cols[0].metric("🇭🇺 Max", f"{hu['max']:.1f} °C")
        metric_cols[0].metric("🇭🇺 Min", f"{hu['min']:.1f} °C")

        export_row = {
            "Dátum": date_selected.strftime("%Y-%m-%d"),
            "Országos maximum": hu["max"],
            "Országos minimum": hu["min"],
        }

        for i, city in enumerate(CITIES, start=1):
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)]
            ext = calc_extremes(df_city)

            metric_cols[i].metric(
                f"{city} max",
                f"{ext['max']:.1f} °C" if pd.notna(ext["max"]) else "–",
            )
            metric_cols[i].metric(
                f"{city} min",
                f"{ext['min']:.1f} °C" if pd.notna(ext["min"]) else "–",
            )

            export_row[f"{city} maximum"] = ext["max"]
            export_row[f"{city} minimum"] = ext["min"]

        # -------------------------------------------------
        # VÁROSI TÁBLÁZATOK (EXPANDER)
        # -------------------------------------------------
        st.subheader("🏙️ Városi állomások")

        for city in CITIES:
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)]
            if df_city.empty:
                continue

            with st.expander(city, expanded=False):
                numeric = prepare_table(df_city)
                display = format_for_display(numeric)

                st.dataframe(
                    display.style.apply(
                        style_extremes(numeric), axis=1
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        # -------------------------------------------------
        # LETÖLTÉSEK
        # -------------------------------------------------
        st.subheader("⬇️ Letöltések")
        d1, d2 = st.columns(2)

        with d1:
            st.download_button(
                "📦 Eredeti ZIP",
                data=st.session_state["zip_bytes"],
                file_name=st.session_state["zip_name"],
                mime="application/zip",
            )

        with d2:
            export_df = pd.DataFrame([[
                export_row.get("Dátum"),
                export_row.get("Országos maximum"),
                export_row.get("Országos minimum"),
                export_row.get("Budapest maximum"),
                export_row.get("Budapest minimum"),
                export_row.get("Debrecen maximum"),
                export_row.get("Debrecen minimum"),
                export_row.get("Győr maximum"),
                export_row.get("Győr minimum"),
                export_row.get("Miskolc maximum"),
                export_row.get("Miskolc minimum"),
                export_row.get("Pécs maximum"),
                export_row.get("Pécs minimum"),
                export_row.get("Szeged maximum"),
                export_row.get("Szeged minimum"),
            ]],
            columns=[
                "Dátum",
                "Országos maximum",
                "Országos minimum",
                "Budapesti maximum",
                "Budapesti minimum",
                "Debreceni maximum",
                "Debreceni minimum",
                "Győri maximum",
                "Győri minimum",
                "Miskolci maximum",
                "Miskolci minimum",
                "Pécsi maximum",
                "Pécsi minimum",
                "Szegedi maximum",
                "Szegedi minimum",
            ])

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                export_df.to_excel(writer, index=False)

            st.download_button(
                "📊 Excel export",
                data=buffer.getvalue(),
                file_name=f"napi_homerseklet_{date_selected}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"Hiba történt: {e}")
