import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Hőmérséklet-Előrejelző Dashboard", layout="wide", page_icon="🌡️")

# Egyedi stílus a modern dashboard megjelenéshez
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .info-box { background-color: #f8f9fa; padding: 18px; border-radius: 10px; font-size: 0.85rem; border-left: 5px solid #0d6efd; line-height: 1.6; }
    .source-tag { font-size: 0.75rem; color: #6c757d; margin-top: 10px; display: block; }
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ---
HU_COORDS = [(16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05), (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40), (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25), (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# VÁROSLISTA (Érd azonosításhoz kiemelve)
CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Pécs", "lat": 46.07, "lon": 18.23},
    {"n": "Győr", "lat": 47.68, "lon": 17.63}, {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41},
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Szolnok", "lat": 47.17, "lon": 20.18},
    {"n": "Tatabánya", "lat": 47.58, "lon": 18.40}, {"n": "Sopron", "lat": 47.68, "lon": 16.59},
    {"n": "Kaposvár", "lat": 46.35, "lon": 17.78}, {"n": "Veszprém", "lat": 47.09, "lon": 17.91},
    {"n": "Eger", "lat": 47.90, "lon": 20.37}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- ADATLEKÉRÉS SZÁZALÉKJELZŐVEL ---
def FETCH_FINAL_DATA(date):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    lats = np.arange(45.8, 48.6, 0.15) 
    lons = np.arange(16.2, 22.8, 0.18)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la); v_lons.append(lo)

    total_points = len(v_lats)
    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    weights = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    
    # Folyamatjelző inicializálása
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    chunk_size = 10 
    for i in range(0, total_points, chunk_size):
        # Százalék kiszámítása és megjelenítése
        percent = int((i / total_points) * 100)
        progress_bar.progress(percent)
        status_text.text(f"Adatok feldolgozása az Open-Meteo rácshálón: {percent}%")
        
        curr_lats = v_lats[i:i+chunk_size]
        curr_lons = v_lons[i:i+chunk_size]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": curr_lats, "longitude": curr_lons, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }, timeout=10).json()
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    if 'hourly' in p:
                        results[i+j]["min"] += min(p['hourly']['temperature_2m']) * w
                        results[i+j]["max"] += max(p['hourly']['temperature_2m']) * w
            except: continue
            
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(results)

# --- DASHBOARD FELÜLET ---
main_col, side_col = st.columns([3.2, 1], gap="large")

with main_col:
    st.title("🌡️ Súlyozott Modell-Előrejelzés")
    
    d_c1, d_c2 = st.columns([2, 1])
    target_date = d_c1.date_input("Választott dátum", datetime.now() + timedelta(days=1))
    if d_c2.button("🔄 Adatok frissítése", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # Adatfeldolgozás futtatása
    df = FETCH_FINAL_DATA(target_date)
    
    if not df.empty:
        min_row, max_row = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        
        m_c1, m_c2 = st.columns(2)
        m_c1.metric("📉 Országos Minimum", f"{round(min_row['min'], 1)} °C", f"{find_nearest_city(min_row['lat'], min_row['lon'])} környéke")
        m_c2.metric("📈 Országos Maximum", f"{round(max_row['max'], 1)} °C", f"{find_nearest_city(max_row['lat'], max_row['lon'])} környéke")
        
        st.divider()
        
        map_c1, map_c2 = st.columns(2)
        def draw_map(data, val, colors, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=val, color_continuous_scale=colors, 
                                    zoom=6.0, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', 
                                           line=dict(width=2, color='#444'), showlegend=False))
            fig.update_layout(title=title, margin={"r":0,"t":35,"l":0,"b":0}, height=450)
            return fig
        
        map_c1.plotly_chart(draw_map(df, "min", "Viridis", "Minimum"), use_container_width=True)
        map_c2.plotly_chart(draw_map(df, "max", "Reds", "Maximum"), use_container_width=True)

with side_col:
    st.subheader("⚙️ Szakmai Háttér")
    st.markdown("""
    <div class="info-box">
    <b>Adatforrás:</b><br>
    Az <b>Open-Meteo API</b> aggregált adatai alapján (ECMWF, GFS, ICON modellek).
    <br><br>
    <b>Éghajlati nap (WMO):</b><br>
    A mérés minden nap 18:00 UTC (19:00 CET) és a következő nap 18:00 UTC között zajlik.
    <br><br>
    <b>Rácsháló:</b><br>
    A számítás sűrű, $0.15^{\circ} \times 0.18^{\circ}$-os felbontáson alapul, amely segít a domborzati különbségek (fagyzugok) leképezésében.
    <br>
    <span class="source-tag">A betöltési sáv a rácspontok és modellek feldolgozási állapotát jelzi.</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("---")
    
    # Modell súlyozás kördiagram
    w_df = pd.DataFrame({"Modell": ["ECMWF (45%)", "GFS (30%)", "ICON (25%)"], "Súly": [45, 30, 25]})
    fig_w = px.pie(w_df, values='Súly', names='Modell', hole=0.5, color_discrete_sequence=px.colors.sequential.Teal)
    fig_w.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.5, xanchor="center", x=0.5), margin=dict(t=0, b=0, l=0, r=0), height=300)
    st.plotly_chart(fig_w, use_container_width=True)
