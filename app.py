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
    res = {"min": None, "max": None}

    if not df["min_val"].dropna().empty:
        idx = df["min_val"].idxmin()
        res["min"] = (df.loc[idx, "min_val"], df.loc[idx, "station_full"])

    if not df["max_val"].dropna().empty:
        idx = df["max_val"].idxmax()
        res["max"] = (df.loc[idx, "max_val"], df.loc[idx, "station_full"])

    return res


def styled_table(df):
    min_v = df["Minimum (°C)"].min()
    max_v = df["Maximum (°C)"].max()

    def style(row):
        return [
            "font-weight: bold; color: blue"
            if col == "Minimum (°C)" and row[col] == min_v
            else "font-weight: bold; color: red"
            if col == "Maximum (°C)" and row[col] == max_v
            else ""
            for col in row.index
        ]

    return df.style.apply(style, axis=1)


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(page_title="Városi hőmérsékleti riport", layout="centered")

st.title("🌡️ Napi hőmérsékleti riport – országos és városi bontás")
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

        # -------------------------------
        # ORSZÁGOS
        # -------------------------------
        st.subheader("🇭🇺 Országos hőmérsékleti szélsők")
        hu_ext = calc_extremes(df)

        c1, c2 = st.columns(2)
        c1.metric("🔥 Maximum", f"{hu_ext['max'][0]} °C", hu_ext["max"][1])
        c2.metric("❄️ Minimum", f"{hu_ext['min'][0]} °C", hu_ext["min"][1])

        export_row = {
            "Dátum": date_selected.strftime("%Y-%m-%d"),
            "Országos max": hu_ext["max"][0],
            "Országos min": hu_ext["min"][0],
        }

        st.divider()

        # -------------------------------
        # VÁROSOK
        # -------------------------------
        for city in CITIES:
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)].copy()
            if df_city.empty:
                continue

            st.subheader(f"🏙️ {city}")
            ext = calc_extremes(df_city)

            c1, c2 = st.columns(2)
            if ext["max"]:
                c1.metric("🔥 Maximum", f"{ext['max'][0]} °C", ext["max"][1])
            if ext["min"]:
                c2.metric("❄️ Minimum", f"{ext['min'][0]} °C", ext["min"][1])

            export_row[f"{city} max"] = ext["max"][0]
            export_row[f"{city} min"] = ext["min"][0]

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
                styled_table(table_df),
                use_container_width=True,
                hide_index=True,
            )

            st.divider()

        # -------------------------------
        # EXCEL EXPORT
        # -------------------------------
        st.subheader("⬇️ Excel export")

        export_df = pd.DataFrame(
            [[
                export_row.get("Dátum"),
                export_row.get("Országos max"),
                export_row.get("Országos min"),
                export_row.get("Budapest max"),
                export_row.get("Budapest min"),
                export_row.get("Debrecen max"),
                export_row.get("Debrecen min"),
                export_row.get("Győr max"),
                export_row.get("Győr min"),
                export_row.get("Miskolc max"),
                export_row.get("Miskolc min"),
                export_row.get("Pécs max"),
                export_row.get("Pécs min"),
                export_row.get("Szeged max"),
                export_row.get("Szeged min"),
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
            ],
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Napi adatok")

        st.download_button(
            "📥 Excel fájl letöltése",
            data=buffer.getvalue(),
            file_name=f"napi_homersekleti_adatok_{date_selected}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"Hiba történt: {e}")
