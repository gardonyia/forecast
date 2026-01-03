import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Modell-Súlyozó Dashboard", layout="wide", page_icon="🌡️")

# UI Stílus beállítása
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .info-box { background-color: #f8f9fa; padding: 18px; border-radius: 10px; font-size: 0.85rem; border-left: 5px solid #0d6efd; line-height: 1.6; }
    .help-text-italic { font-size: 0.75rem; color: #6c757d; font-style: italic; display: flex; align-items: center; height: 100%; padding-top: 25px; }
    .tech-card { background-color: #ffffff; padding: 20px; border-radius: 10px; border: 1px solid #e9ecef; margin-bottom: 20px; }
    /* Gomb vertikális igazítása és méretezése */
    div[data-testid="stButton"] { margin-top: 28px; width: fit-content; }
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ---
HU_COORDS = [(16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05), (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40), (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25), (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Pécs", "lat": 46.07, "lon": 18.23}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- ADATLEKÉRÉS ---
@st.cache_data(ttl=3600)
def FETCH_FINAL_DATA(date):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    lats, lons = np.arange(45.8, 48.6, 0.15), np.arange(16.2, 22.8, 0.18)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)): v_lats.append(la); v_lons.append(lo)

    total_points = len(v_lats)
    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    weights = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    
    prog = st.progress(0)
    stat = st.empty()
    
    for i in range(0, total_points, 10):
        percent = int((i / total_points) * 100)
        prog.progress(percent)
        stat.text(f"Adatok lekérése az Open-Meteo szerveréről: {percent}%")
        
        curr_la, curr_lo = v_lats[i:i+10], v_lons[i:i+10]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": curr_la, "longitude": curr_lo, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }, timeout=10).json()
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    if 'hourly' in p:
                        results[i+j]["min"] += min(p['hourly']['temperature_2m']) * w
                        results[i+j]["max"] += max(p['hourly']['temperature_2m']) * w
            except: continue
    prog.empty(); stat.empty()
    return pd.DataFrame(results)

# --- DASHBOARD ---
main_c, side_c = st.columns([3, 1], gap="large")

with main_c:
    st.title("🌡️ Súlyozott Modell-Előrejelzés")
    
    # Vezérlők: Dátum | Ikon Gomb | Dőlt Leírás
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.2, 0.3, 2.5])
    
    target_date = ctrl_col1.date_input("Dátum választása", datetime.now() + timedelta(days=1))
    
    if ctrl_col2.button("🔄"):
        st.cache_data.clear()
        st.rerun()
        
    ctrl_col3.markdown('<div class="help-text-italic">Friss modellfutások betöltéséhez vagy hiba elhárításához.</div>', unsafe_allow_html=True)
    
    df = FETCH_FINAL_DATA(target_date)
    
    if not df.empty:
        min_r, max_r = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        mc1, mc2 = st.columns(2)
        mc1.metric("📉 Országos Minimum", f"{round(min_r['min'], 1)} °C", f"{find_nearest_city(min_r['lat'], min_r['lon'])} környéke")
        mc2.metric("📈 Országos Maximum", f"{round(max_r['max'], 1)} °C", f"{find_nearest_city(max_r['lat'], max_r['lon'])} környéke")
        
        mapc1, mapc2 = st.columns(2)
        def draw_m(data, val, col, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=val, color_continuous_scale=col, zoom=6.0, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', line=dict(width=2, color='#444'), showlegend=False))
            fig.update_layout(title=title, margin={"r":0,"t":35,"l":0,"b":0}, height=450)
            return fig
        mapc1.plotly_chart(draw_m(df, "min", "Viridis", "Minimum Hőtérkép"), use_container_width=True)
        mapc2.plotly_chart(draw_m(df, "max", "Reds", "Maximum Hőtérkép"), use_container_width=True)

with side_c:
    st.subheader("⚙️ Szakmai Kivonat")
    st.markdown("""
    <div class="info-box">
    <b>Adatforrás:</b> Open-Meteo API.<br><br>
    <b>Súlyozás:</b> ECMWF (45%), GFS (30%), ICON (25%)<br><br>
    <b>Éghajlati nap:</b> 18:00 UTC - 18:00 UTC.
    </div>
    """, unsafe_allow_html=True)
    
    w_df = pd.DataFrame({"Modell": ["ECMWF", "GFS", "ICON"], "Súly": [45, 30, 25]})
    fig_p = px.pie(w_df, values='Súly', names='Modell', hole=0.5, color_discrete_sequence=px.colors.sequential.Teal)
    fig_p.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300, showlegend=True, legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_p, use_container_width=True)

# --- BŐVEBB TECHNIKAI LEÍRÁS ---
st.divider()
st.subheader("📘 Bővebb technikai leírás")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("""
    ### 1. Adatgyűjtés és Rácsháló
    A program nem egyetlen pontra kér le adatot, hanem egy **virtuális rácshálót** fektet Magyarország térképére.
    * **Pontosság:** A rácspontok felbontása ($0.15^{\circ} \\times 0.18^{\circ}$) lehetővé teszi a lokális különbségek (pl. völgyek, fagyzugok) detektálását.
    * **Szűrés:** Csak az országhatáron belüli pontokat dolgozzuk fel geofencing eljárással.
    
    ### 2. Multi-Modell Ensemble Súlyozás
    Az eredmény három globális modell súlyozott kombinációja:
    * **ECMWF (45%):** Az európai csúcsmodell.
    * **GFS (30%):** Az amerikai globális modell.
    * **ICON (25%):** A német precíziós modell.
    """)

with col_b:
    st.markdown("""
    ### 3. Az "Éghajlati Nap" Logikája
    A mérés **18:00 UTC-től** a következő nap **18:00 UTC-ig** tart. Ez biztosítja, hogy a napi minimum (hajnal) és maximum (délután) egyazon statisztikai egységbe kerüljön.

    ### 4. Megjelenítés
    A térképek interaktívak: az egérrel belenagyíthat az egyes régiókba. A színskálák (Viridis és Reds) a meteorológiai vizualizációk szabványaihoz igazodnak.
    """)

st.info("💡 Tipp: Az ikon gomb (🔄) megnyomásával törölheted a korábbi mentett adatokat, ha gyanítod, hogy új modellfutás vált elérhetővé.")
