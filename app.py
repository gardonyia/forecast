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
    return {
        "min": df["min_val"].min(),
        "max": df["max_val"].max(),
    }


def prepare_table(df_city):
    return (
        df_city[["station_name", "station_number", "min_val", "max_val"]]
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


def style_table(df_numeric):
    min_v = df_numeric["Minimum (°C)"].min()
    max_v = df_numeric["Maximum (°C)"].max()

    def style(row):
        styles = []
        for col in row.index:
            if col == "Minimum (°C)" and row[col] == min_v:
                styles.append("color:#1f77b4;font-weight:bold;")
            elif col == "Maximum (°C)" and row[col] == max_v:
                styles.append("color:#d62728;font-weight:bold;")
            else:
                styles.append("")
        return styles

    return style


def city_metric(city, ext):
    max_v = f"{ext['max']:.1f} °C" if pd.notna(ext["max"]) else "–"
    min_v = f"{ext['min']:.1f} °C" if pd.notna(ext["min"]) else "–"

    st.markdown(
        f"""
        <div style="
            border:1px solid #ddd;
            border-radius:10px;
            padding:10px;
            text-align:center;
            background-color:#fafafa;
        ">
            <div style="font-size:1.2em;font-weight:600;margin-bottom:4px;">
                {city}
            </div>
            <div style="font-size:1em;color:#d62728;">Max: {max_v}</div>
            <div style="font-size:1em;color:#1f77b4;">Min: {min_v}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(page_title="Napi hőmérsékleti riport", layout="wide")

st.title("🌡️ Napi hőmérsékleti riport")
st.caption("Forrás: HungaroMet – napi szinoptikus jelentések")

ctrl_col, _ = st.columns([1, 4])
with ctrl_col:
    date_selected = st.date_input(
        "📅 Dátum",
        value=datetime.now(ZoneInfo("Europe/Budapest")).date() - timedelta(days=1),
    )
    load = st.button("📥 Betöltés")

if load:
    try:
        fname = build_filename_for_date(date_selected)
        zip_bytes = download_zip_bytes(BASE_INDEX_URL + fname)
        csv_text = extract_csv_from_zipbytes(zip_bytes, fname.replace(".zip", ""))
        df = parse_data(csv_text)

        st.session_state["zip_bytes"] = zip_bytes
        st.session_state["zip_name"] = fname

        # ---------------- DASHBOARD ----------------
        st.subheader("📊 Összefoglaló")

        metric_cols = st.columns(7)
        hu = calc_extremes(df)
        city_metric("🇭🇺 Országos", hu)

        export_row = {
            "Dátum": date_selected.strftime("%Y-%m-%d"),
            "Országos maximum": hu["max"],
            "Országos minimum": hu["min"],
        }

        for i, city in enumerate(CITIES):
            with metric_cols[i + 1]:
                df_city = df[df["station_name"].str.contains(city, case=False, na=False)]
                ext = calc_extremes(df_city)
                city_metric(city, ext)
                export_row[f"{city} maximum"] = ext["max"]
                export_row[f"{city} minimum"] = ext["min"]

        # ---------------- TÁBLÁZATOK ----------------
        st.subheader("🏙️ Városi állomások")

        table_cols = st.columns(2)
        for i, city in enumerate(CITIES):
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)]
            if df_city.empty:
                continue

            with table_cols[i % 2]:
                with st.expander(city, expanded=False):
                    num = prepare_table(df_city)
                    disp = format_for_display(num)
                    st.dataframe(
                        disp.style
                        .apply(style_table(num), axis=1)
                        .set_table_styles(
                            [
                                {"selector": "th", "props": [("background-color", "#f0f0f0"), ("border", "1px solid #ccc")]},
                                {"selector": "td", "props": [("border", "1px solid #ddd")]},
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        # ---------------- LETÖLTÉS ----------------
        st.subheader("⬇️ Letöltések")
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
