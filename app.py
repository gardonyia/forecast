import io
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

# Halvány háttérképek (public URL). Ha a környezet blokkolja, simán csak nem látszik.
CITY_BACKGROUNDS = {
    "Országos": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Flag_of_Hungary.svg/1280px-Flag_of_Hungary.svg.png",
    "Budapest": "https://images.unsplash.com/photo-1549640376-8cc6b7c2f42f?auto=format&fit=crop&w=1200&q=60",
    "Debrecen": "https://images.unsplash.com/photo-1526481280695-3c687fd5432c?auto=format&fit=crop&w=1200&q=60",
    "Győr": "https://images.unsplash.com/photo-1520962922320-2038eebab146?auto=format&fit=crop&w=1200&q=60",
    "Miskolc": "https://images.unsplash.com/photo-1523731407965-2430cd12f5e4?auto=format&fit=crop&w=1200&q=60",
    "Pécs": "https://images.unsplash.com/photo-1523419409543-a5e549c1faa3?auto=format&fit=crop&w=1200&q=60",
    "Szeged": "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&fit=crop&w=1200&q=60",
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
                styles.append("color:#1f77b4;font-weight:700;")
            elif col == "Maximum (°C)" and row[col] == max_v:
                styles.append("color:#d62728;font-weight:700;")
            else:
                styles.append("")
        return styles

    return row_style


def card_html(title, ext, bg_url, opacity=0.10):
    max_txt = f"{ext['max']:.1f} °C" if pd.notna(ext["max"]) else "Nincs adat"
    min_txt = f"{ext['min']:.1f} °C" if pd.notna(ext["min"]) else "Nincs adat"

    # Font-hierarchia: városnév nagyobb, értékek kicsit kisebb, de tiszták.
    return f"""
    <div style="
        position:relative;
        border:1px solid rgba(0,0,0,0.10);
        border-radius:14px;
        padding:14px 14px 12px 14px;
        background:#ffffff;
        box-shadow:0 6px 18px rgba(0,0,0,0.06);
        overflow:hidden;
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    ">
        <div style="
            position:absolute; inset:0;
            background-image:url('{bg_url}');
            background-size:cover;
            background-position:center;
            opacity:{opacity};
        "></div>

        <div style="position:relative;">
            <div style="font-size:18px;font-weight:800; line-height:1.2; margin-bottom:8px;">
                {title}
            </div>

            <div style="display:flex; gap:10px; align-items:baseline; justify-content:space-between;">
                <div style="font-size:14px; font-weight:700; color:#d62728;">
                    🔥 Max
                </div>
                <div style="font-size:20px; font-weight:800; color:#111;">
                    {max_txt}
                </div>
            </div>

            <div style="display:flex; gap:10px; align-items:baseline; justify-content:space-between; margin-top:6px;">
                <div style="font-size:14px; font-weight:700; color:#1f77b4;">
                    ❄️ Min
                </div>
                <div style="font-size:20px; font-weight:800; color:#111;">
                    {min_txt}
                </div>
            </div>
        </div>
    </div>
    """


def render_card(title, ext, kind_key, height=130):
    bg = CITY_BACKGROUNDS.get(kind_key, "")
    html = card_html(title=title, ext=ext, bg_url=bg, opacity=0.10)
    # components.html iframe-ben renderel. Ez nem fog tagokat kiírni szövegként.
    components.html(html, height=height)


def build_export_dataframe(date_selected, values_by_city):
    # values_by_city: dict like {"Országos": {"max":..., "min":...}, "Budapest":..., ...}
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
st.title("🌡️ Napi hőmérsékleti riport")
st.caption("Forrás: HungaroMet – napi szinoptikus jelentések. A háttérképek halványak, hogy olvasható maradjon minden.")

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

        # előkészítjük az exporthoz is
        values = {"Országos": calc_extremes(df)}
        for city in CITIES:
            df_city = df[df["station_name"].str.contains(city, case=False, na=False)]
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

    # 1) Országos szekció
    st.header("🇭🇺 Országos adatok")
    render_card("Országos", values["Országos"], kind_key="Országos", height=140)

    # Letöltések (országos alatt, logikus helyen)
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📦 Eredeti ZIP letöltése",
            data=st.session_state["zip_bytes"],
            file_name=st.session_state["zip_name"],
            mime="application/zip",
        )

    with dl2:
        export_df = build_export_dataframe(date_selected, values)
        buf = io.BytesIO()
        # A2-től: header A1-ben, adat A2-ben (alapértelmezett to_excel)
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            export_df.to_excel(w, index=False, sheet_name="Napi adatok")
        st.download_button(
            "📊 Excel export letöltése",
            data=buf.getvalue(),
            file_name=f"napi_homerseklet_{date_selected}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.divider()

    # 2) Városok szekció
    st.header("🏙️ Városi adatok")

    # Városi kártyák gridben (kevesebb görgetés)
    # 3 oszlopos grid általában jól olvasható normál layouton.
    cols = st.columns(3)
    for i, city in enumerate(CITIES):
        with cols[i % 3]:
            render_card(city, values[city], kind_key=city, height=140)

    st.subheader("📋 Városi állomások (részletek)")
    # Táblázatok 2 oszlopban, expanderekben
    tcols = st.columns(2)
    for i, city in enumerate(CITIES):
        df_city = df[df["station_name"].str.contains(city, case=False, na=False)].copy()
        with tcols[i % 2]:
            with st.expander(city, expanded=False):
                numeric = prepare_table(df_city)
                display = format_for_display(numeric)

                styled = (
                    display.style
                    .apply(style_table(numeric), axis=1)
                    .set_table_styles([
                        {"selector": "th", "props": [("background-color", "#f3f4f6"),
                                                     ("border", "1px solid #cbd5e1"),
                                                     ("padding", "6px"),
                                                     ("font-weight", "700")]},
                        {"selector": "td", "props": [("border", "1px solid #e2e8f0"),
                                                     ("padding", "6px")]},
                        {"selector": "table", "props": [("border-collapse", "collapse"),
                                                        ("width", "100%")]},
                    ])
                )

                st.dataframe(styled, use_container_width=True, hide_index=True)
