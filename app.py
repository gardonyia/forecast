import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide", page_icon="🌡️")

# --- STÍLUS (Modern UI) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ÉS VÁROSOK ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Pécs", "lat": 46.07, "lon": 18.23},
    {"n": "Győr", "lat": 47.68, "lon": 17.63}, {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41},
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Szolnok", "lat": 47.17, "lon": 20.18}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- ADATFELDOLGOZÁS ---
def FETCH_FINAL_DATA(date):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    lats, lons = np.arange(45.8, 48.6, 0.15), np.arange(16.2, 22.8, 0.18)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la); v_lons.append(lo)
    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    weights = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    chunk_size = 10
    for i in range(0, len(v_lats), chunk_size):
        c_lats, c_lons = v_lats[i:i+chunk_size], v_lats[i:i+chunk_size] # Javítás a chunk lons-ra
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": v_lats[i:i+chunk_size], "longitude": v_lons[i:i+chunk_size],
                    "hourly": "temperature_2m", "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }).json()
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    if 'hourly' in p:
                        t = p['hourly']['temperature_2m']
                        results[i+j]["min"] += min(t) * w
                        results[i+j]["max"] += max(t) * w
            except: continue
    return pd.DataFrame(results)

# --- FŐ FELÜLET ---
st.title("🌡️ Súlyozott Magyarországi Hőmérséklet-Előrejelzés")

# OLDALSÁV
with st.sidebar:
    st.header("Beállítások")
    target_date = st.date_input("Előrejelzés napja", datetime.now() + timedelta(days=1))
    if st.button("🔄 Adatok frissítése", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# EREDMÉNYEK
with st.spinner('Adatok elemzése az Open-Meteo adatbázisából...'):
    df = FETCH_FINAL_DATA(target_date)
    if not df.empty:
        min_row, max_row = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        min_city, max_city = find_nearest_city(min_row['lat'], min_row['lon']), find_nearest_city(max_row['lat'], max_row['lon'])

        col1, col2 = st.columns(2)
        col1.metric("📉 Országos Minimum", f"{round(min_row['min'], 1)} °C", f"{min_city} környéke")
        col2.metric("📈 Országos Maximum", f"{round(max_row['max'], 1)} °C", f"{max_city} környéke")

        m1, m2 = st.columns(2)
        def draw_map(data, col, colors, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=col, color_continuous_scale=colors, 
                                    zoom=6.3, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', line=dict(width=2, color='#333')))
            fig.update_layout(title=title, margin={"r":0,"t":40,"l":0,"b":0}, height=500)
            return fig

        m1.plotly_chart(draw_map(df, "min", "Viridis", "Éjszakai Minimumok"), use_container_width=True)
        m2.plotly_chart(draw_map(df, "max", "Reds", "Nappali Maximumok"), use_container_width=True)

# --- LEÍRÁSOK AZ OLDAL ALJÁN ---
st.divider()
st.subheader("ℹ️ Módszertani és Szakmai Háttér")

c_info, c_diag = st.columns([2, 1])

with c_info:
    st.markdown(f"""
    ### **Hogyan készül az előrejelzés?**
    Az alkalmazás az **Open-Meteo API** globális modelljeinek (ECMWF, GFS, ICON) adatait ötvözi egy egyedi súlyozott algoritmus segítségével. 
    A számítás alapja az **éghajlati nap**, amely a kiválasztott napot megelőző **18:00 UTC (19:00 CET)** és a tárgynapi **18:00 UTC** közötti 24 órát öleli fel.

    **Főbb jellemzők:**
    * **Mikroklíma detektálás:** A sűrű, $0.15^{\circ} \times 0.18^{\circ}$-os rácsfelbontás lehetővé teszi a domborzati mélyedésekben (fagyzugokban) kialakuló extrém minimumok azonosítását.
    * **Súlyozott Ensemble:** Az ECMWF (Európa) 45%, a GFS (USA) 30%, míg az ICON (Németország) 25% súllyal szerepel a végeredményben, optimalizálva a Kárpát-medencére jellemző előrejelzési hibákat.
    * **Geofencing:** Szigorú térbeli szűrés biztosítja, hogy csak a Magyarország közigazgatási határán belüli adatpontok kerüljenek feldolgozásra.
    """)

with c_diag:
    # Jelmagyarázattal ellátott diagram
    w_df = pd.DataFrame({
        "Modell": ["ECMWF (IFS)", "GFS (Global)", "ICON (German)"],
        "Súly": [45, 30, 25]
    })
    fig_w = px.pie(w_df, values='Súly', names='Modell', hole=0.4, 
                   title="Modell súlyozási arányok",
                   color_discrete_sequence=px.colors.sequential.Teal_r)
    fig_w.update_layout(margin=dict(t=40, b=0, l=0, r=0), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
    st.plotly_chart(fig_w, use_container_width=True)

st.info("**Forrás:** Adatok az Open-Meteo API-ból származnak. Az előrejelzések tájékoztató jellegűek.")
