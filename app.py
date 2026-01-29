import io
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------
# KONFIGURÁCIÓ
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
    result = {"min": None, "max": None}

    if not df["min_val"].dropna().empty:
        idx = df["min_val"].idxmin()
        result["min"] = df.loc[idx, "min_val"]

    if not df["max_val"].dropna().empty:
        idx = df["max_val"].idxmax()
        result["max"] = df.loc[idx, "max_val"]

    return result


def prepare_table(df_city):
    table = (
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
    return table


def format_for_display(df):
    df_disp = df.copy()
    for col in ["Minimum (°C)", "Maximum (°C)"]:
        df_disp[col] = df_disp[col].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else "Nincs adat"
        )
    return df_disp


def style_extremes(df_numeric):
    min_val = df_numeric["Minimum (°C)"].min()
    max_val = df_numeric["Maximum (°C)"].max()

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
st.set_page_config(page_title="Napi hőmérsékleti riport", layout="centered")

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

        # ---------------------------------------------
        # ORSZÁGOS
        # ---------------------------------------------
        st.subheader("🇭🇺 Országos hőmérsékleti szélsők")
        hu_ext = calc_extremes(df)

        c1, c2 = st.columns(2)
        c1.metric("🔥 Maximum", f"{hu_ext['max']:.1f} °C")
        c2.metric("❄️ Minimum", f"{hu_ext['min']:.1f} °C")

        export_row = {
            "Dátum": date_selected.strftime("%Y-%m-%d"),
            "Országos maximum": hu_ext["max"],
            "Országos minimum": hu_ext["min"],
        }

        st.divider()

        # ---------------------------------------------
        # VÁROSOK
        # ---------------------------------------------
        for city in CITIES:
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)].copy()
            if df_city.empty:
                continue

            st.subheader(f"🏙️ {city}")
            ext = calc_extremes(df_city)

            c1, c2 = st.columns(2)
            if ext["max"] is not None:
                c1.metric("🔥 Maximum", f"{ext['max']:.1f} °C")
            if ext["min"] is not None:
                c2.metric("❄️ Minimum", f"{ext['min']:.1f} °C")

            export_row[f"{city} maximum"] = ext["max"]
            export_row[f"{city} minimum"] = ext["min"]

            numeric_table = prepare_table(df_city)
            display_table = format_for_display(numeric_table)

            st.dataframe(
                display_table.style.apply(
                    style_extremes(numeric_table), axis=1
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.divider()

        # ---------------------------------------------
        # EXCEL EXPORT
        # ---------------------------------------------
        st.subheader("⬇️ Excel export")

        export_df = pd.DataFrame(
            [[
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
            ],
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Napi adatok")

        st.download_button(
            "📥 Excel letöltése",
            data=buffer.getvalue(),
            file_name=f"napi_homerseklet_{date_selected}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"Hiba történt: {e}")
