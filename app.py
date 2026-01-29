import io
import re
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------
# KONFIG
# ---------------------------------------------------------
BASE_INDEX_URL = "https://odp.met.hu/weather/weather_reports/synoptic/hungary/daily/csv/"

CITIES = ["Budapest", "Debrecen", "Győr", "Miskolc", "Pécs", "Szeged"]

# Kártyákhoz enyhe háttérszínek (városonként külön, hogy vizuálisan tagoljon)
CARD_BG = {
    "Országos": "#f6f7fb",
    "Budapest": "#f4fbff",
    "Debrecen": "#f7fbf4",
    "Győr": "#fff8f2",
    "Miskolc": "#f9f4ff",
    "Pécs": "#fffdf2",
    "Szeged": "#f2fff9",
}

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
    return {"min": df["min_val"].min(), "max": df["max_val"].max()}


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
    out = df.copy()
    for col in ["Minimum (°C)", "Maximum (°C)"]:
        out[col] = out[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "Nincs adat")
    return out


def style_table(df_numeric):
    min_v = df_numeric["Minimum (°C)"].min()
    max_v = df_numeric["Maximum (°C)"].max()

    def row_style(row):
        styles = []
        for col in row.index:
            if col == "Minimum (°C)" and row[col] == min_v:
                styles.append("color:#1f77b4;font-weight:800;")
            elif col == "Maximum (°C)" and row[col] == max_v:
                styles.append("color:#d62728;font-weight:800;")
            else:
                styles.append("")
        return styles

    return row_style


def city_pattern(city: str) -> re.Pattern:
    """
    Szűrés: a városnév csak "önálló token" legyen:
    - megengedett: 'Győr', 'Győr-Újváros', 'Győr xyz'
    - kizárt: 'Győrsövényház', 'Diósgyőr'
    Logika: elején szóhatár / nem betű, majd városnév, utána szóvég / nem betű.
    """
    # A magyar ékezetes betűket is vegyük betűnek: \w nem tökéletes, ezért explicit kizárás.
    # Egyszerű és működő: előtte ne legyen betű, utána ne legyen betű.
    return re.compile(rf"(?<![A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]){re.escape(city)}(?![A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])", re.IGNORECASE)


CITY_PATTERNS = {c: city_pattern(c) for c in CITIES}


def filter_city(df: pd.DataFrame, city: str) -> pd.DataFrame:
    pat = CITY_PATTERNS[city]
    # station_name lehet NaN, ezért na=False
    return df[df["station_name"].astype(str).str.contains(pat, na=False)].copy()


def card_html(title, ext, bg_color):
    max_txt = f"{ext['max']:.1f} °C" if pd.notna(ext["max"]) else "Nincs adat"
    min_txt = f"{ext['min']:.1f} °C" if pd.notna(ext["min"]) else "Nincs adat"

    return f"""
    <div style="
        border:1px solid rgba(0,0,0,0.10);
        border-radius:14px;
        padding:14px 14px 12px 14px;
        background:{bg_color};
        box-shadow:0 6px 18px rgba(0,0,0,0.06);
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    ">
        <div style="font-size:18px;font-weight:900; line-height:1.2; margin-bottom:8px;">
            {title}
        </div>

        <div style="display:flex; justify-content:space-between; align-items:baseline;">
            <div style="font-size:14px; font-weight:800; color:#d62728;">🔥 Max</div>
            <div style="font-size:20px; font-weight:900; color:#111;">{max_txt}</div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:6px;">
            <div style="font-size:14px; font-weight:800; color:#1f77b4;">❄️ Min</div>
            <div style="font-size:20px; font-weight:900; color:#111;">{min_txt}</div>
        </div>
    </div>
    """


def render_card(title, ext, bg_key, height=135):
    html = card_html(title=title, ext=ext, bg_color=CARD_BG.get(bg_key, "#f6f7fb"))
    components.html(html, height=height)


def build_export_dataframe(date_selected, values_by_city):
    row = {
        "Dátum": date_selected.strftime("%Y-%m-%d"),
        "Országos maximum": values_by_city.get("Országos", {}).get("max"),
        "Országos minimum": values_by_city.get("Országos", {}).get("min"),
        "Budapesti maximum": values_by_city.get("Budapest", {}).get("max"),
        "Budapesti minimum": values_by_city.get("Budapest", {}).get("min"),
        "Debreceni maximum": values_by_city.get("Debrecen", {}).get("max"),
        "Debreceni minimum": values_by_city.get("Debrecen", {}).get("min"),
        "Győri maximum": values_by_city.get("Győr", {}).get("max"),
        "Győri minimum": values_by_city.get("Győr", {}).get("min"),
        "Miskolci maximum": values_by_city.get("Miskolc", {}).get("max"),
        "Miskolci minimum": values_by_city.get("Miskolc", {}).get("min"),
        "Pécsi maximum": values_by_city.get("Pécs", {}).get("max"),
        "Pécsi minimum": values_by_city.get("Pécs", {}).get("min"),
        "Szegedi maximum": values_by_city.get("Szeged", {}).get("max"),
        "Szegedi minimum": values_by_city.get("Szeged", {}).get("min"),
    }
    cols = list(row.keys())
    return pd.DataFrame([[row[c] for c in cols]], columns=cols)


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------
for k in ["loaded", "df", "zip_bytes", "zip_name", "values_by_city"]:
    if k not in st.session_state:
        st.session_state[k] = None
if st.session_state["loaded"] is None:
    st.session_state["loaded"] = False

# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.set_page_config(page_title="Napi hőmérsékleti riport", layout="centered")

# Max szélesség: ne legyen vízszintes csúszka
st.markdown(
    """
    <style>
        .block-container {
            max-width: 1200px;
            padding-left: 1.75rem;
            padding-right: 1.75rem;
        }
        .stDataFrame { overflow-x: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

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

        st.session_state["df"] = df
        st.session_state["zip_bytes"] = zip_bytes
        st.session_state["zip_name"] = fname
        st.session_state["loaded"] = True

        values = {"Országos": calc_extremes(df)}
        for city in CITIES:
            df_city = filter_city(df, city)
            values[city] = calc_extremes(df_city)
        st.session_state["values_by_city"] = values

    except Exception as e:
        st.session_state["loaded"] = False
        st.error(f"Hiba történt: {e}")

# ---------------------------------------------------------
# MEGJELENÍTÉS
# ---------------------------------------------------------
if st.session_state["loaded"] and st.session_state["df"] is not None:
    df = st.session_state["df"]
    values = st.session_state["values_by_city"]

    st.header("🇭🇺 Országos adatok")
    render_card("Országos", values["Országos"], bg_key="Országos", height=145)

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📦 Eredeti ZIP letöltése",
            data=st.session_state["zip_bytes"],
            file_name=st.session_state["zip_name"],
            mime="application/zip",
            use_container_width=True,
        )
    with dl2:
        export_df = build_export_dataframe(date_selected, values)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            export_df.to_excel(w, index=False, sheet_name="Napi adatok")
        st.download_button(
            "📊 Excel export letöltése",
            data=buf.getvalue(),
            file_name=f"napi_homerseklet_{date_selected}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()

    st.header("🏙️ Városi adatok")
    cols = st.columns(3)
    for i, city in enumerate(CITIES):
        with cols[i % 3]:
            render_card(city, values[city], bg_key=city, height=145)

    st.subheader("📋 Városi állomások (részletek)")
    tcols = st.columns(2)
    for i, city in enumerate(CITIES):
        df_city = filter_city(df, city)
        with tcols[i % 2]:
            with st.expander(city, expanded=True):
                numeric = prepare_table(df_city)
                display = format_for_display(numeric)

                styled = (
                    display.style
                    .apply(style_table(numeric), axis=1)
                    .set_table_styles([
                        {"selector": "th", "props": [
                            ("background-color", "#f3f4f6"),
                            ("border", "1px solid #cbd5e1"),
                            ("padding", "6px"),
                            ("font-weight", "800"),
                        ]},
                        {"selector": "td", "props": [
                            ("border", "1px solid #e2e8f0"),
                            ("padding", "6px"),
                        ]},
                        {"selector": "table", "props": [
                            ("border-collapse", "collapse"),
                            ("width", "100%"),
                        ]},
                    ])
                )

                st.dataframe(styled, use_container_width=True, hide_index=True)
