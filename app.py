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

# CSS a letisztult kinézethez
st.markdown("""
    <style>
    .main { background-color: #f9f9f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# VÁROSLISTA (Érddel az élen)
CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Pécs", "lat": 46.07, "lon": 18.23},
    {"n": "Győr", "lat": 47.68, "lon": 17.63}, {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41},
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Szolnok", "lat": 47.17, "lon": 20.18},
    {"n": "Tatabánya", "lat": 47.58, "lon": 18.40}, {"n": "Sopron", "lat": 47.68, "lon": 16.59},
    {"n": "Veszprém", "lat": 47.09, "lon": 17.91}, {"n": "Eger", "lat": 47.90, "lon": 20.37}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- ADATLEKÉRÉS ---
def FETCH_DATA(date):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    # Sűrű rácsháló a domborzati pontosságért
    lats = np.arange(45.8, 48.6, 0.15) 
    lons = np.arange(16.2, 22.8, 0.18)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la); v_lons.append(lo)

    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    weights = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    
    chunk_size = 10 
    for i in range(0, len(v_lats), chunk_size):
        c_lats = v_lats[i:i+chunk_size]
        c_lons = v_lons[i:i+chunk_size]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": c_lats, "longitude": c_lons, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }, timeout=10).json()
                
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    if 'hourly' in p:
                        temps = p['hourly']['temperature_2m']
                        results[i+j]["min"] += min(temps) * w
                        results[i+j]["max"] += max(temps) * w
            except: continue
    return pd.DataFrame(results)

# --- FELÜLET ELRENDEZÉSE ---
st.title("🌡️ Magyarországi Modell-Súlyozott Előrejelzés")

with st.sidebar:
    st.header("Beállítások")
    target_date = st.date_input("Választott nap", datetime.now() + timedelta(days=1))
    if st.button("🔄 Adatok frissítése", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# FŐ TARTALOM (Eredmények felül)
with st.spinner('Adatok elemzése az Open-Meteo adatbázisából...'):
    df = FETCH_DATA(target_date)
    
    if not df.empty:
        min_row = df.loc[df['min'].idxmin()]
        max_row = df.loc[df['max'].idxmax()]
        min_city = find_nearest_city(min_row['lat'], min_row['lon'])
        max_city = find_nearest_city(max_row['lat'], max_row['lon'])

        c1, c2 = st.columns(2)
        c1.metric("📉 Országos Minimum", f"{round(min_row['min'], 1)} °C", f"{min_city} környéke")
        c2.metric("📈 Országos Maximum", f"{round(max_row['max'], 1)} °C", f"{max_city} környéke")

        st.divider()
        
        m1, m2 = st.columns(2)
        def draw_map(data, val_col, colors, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=val_col, 
                                    color_continuous_scale=colors, zoom=6.2, 
                                    center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', 
                                           line=dict(width=2, color='black'), showlegend=False))
            fig.update_layout(title=title, margin={"r":0,"t":40,"l":0,"b":0}, height=500)
            return fig

        m1.plotly_chart(draw_map(df, "min", "Viridis", "Éjszakai Minimumok"), use_container_width=True)
        m2.plotly_chart(draw_map(df, "max", "Reds", "Nappali Maximumok"), use_container_width=True)

# SZAKMAI LEÍRÁS (Alul)
st.divider()
st.subheader("📊 Szakmai és Módszertani Háttér")

col_text, col_pie = st.columns([2, 1])

with col_text:
    st.markdown("""
    **Adatforrás:** Az adatok az **Open-Meteo API** szabadon elérhető adatbázisából származnak, amely a világ vezető meteorológiai intézeteinek nyers modellkimeneteit összesíti.
    
    **Módszertan:**
    * **Éghajlati nap:** Az éghajlati statisztikai elvárásoknak megfelelően a mérés a választott napot megelőző este **18:00 UTC**-től a választott nap **18:00 UTC**-ig tart. Ez biztosítja, hogy a hajnali lehűlés és a délutáni felmelegedés egy egységként kerüljön elemzésre.
    * **Sűrű rácsháló:** A $0.15^{\circ} \times 0.18^{\circ}$-os felbontás lehetővé teszi, hogy a domborzati viszonyokat (völgyek, fagyzugok) a modell rácspontjai nagy pontossággal lekövessék.
    * **Modell-súlyozás (Ensemble):** A Kárpát-medence speciális viszonyaira optimalizálva három modell átlagát használjuk (ECMWF, GFS, ICON).
    """)

with col_pie:
    weights_df = pd.DataFrame({
        "Modell": ["ECMWF (Európa)", "GFS (USA)", "ICON (Német)"],
        "Súly": [45, 30, 25]
    })
    fig_pie = px.pie(weights_df, values='Súly', names='Modell', hole=0.4, title="Modellek aránya")
    fig_pie.update_layout(margin=dict(t=30, b=0, l=0, r=0), height=300)
    st.plotly_chart(fig_pie, use_container_width=True)
