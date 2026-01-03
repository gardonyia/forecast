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

# --- GEOMETRIA ÉS HATÁRVONAL ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# Városok a szélsőértékek azonosításához
CITIES = [
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Sopron", "lat": 47.68, "lon": 16.59}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Zalaegerszeg", "lat": 46.84, "lon": 16.84},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Békéscsaba", "lat": 46.68, "lon": 21.09},
    {"n": "Salgótarján", "lat": 48.10, "lon": 19.80}, {"n": "Eger", "lat": 47.90, "lon": 20.37}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- ADATGYŰJTÉS ---
def FETCH_FINAL_DATA(date):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    # Rácsháló (csak belföld)
    lats, lons = np.arange(45.8, 48.6, 0.25), np.arange(16.2, 22.8, 0.35)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la); v_lons.append(lo)

    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    weights = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    
    chunk_size = 15 
    for i in range(0, len(v_lats), chunk_size):
        c_lats, c_lons = v_lats[i:i+chunk_size], v_lons[i:i+chunk_size]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": c_lats, "longitude": c_lons, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }).json()
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    t = p['hourly']['temperature_2m']
                    results[i+j]["min"] += min(t) * w
                    results[i+j]["max"] += max(t) * w
            except: continue
    return pd.DataFrame(results)

# --- FELÜLET ---
st.title("🌡️ Súlyozott Magyarországi Előrejelző")

# KÉTOSZTATÚ LEÍRÁS
with st.expander("ℹ️ Hogyan működik a program? - Ismertető", expanded=True):
    tab1, tab2 = st.tabs(["💡 Közérthető összefoglaló", "⚙️ Technikai háttér"])
    
    with tab1:
        st.write("""
        Ez az alkalmazás nem egyetlen forrásra támaszkodik, hanem három nagy nemzetközi időjárás-előrejelző központ (európai, amerikai és német) adatait egyesíti.
        
        * **Pontosabb becslés:** A különböző modellek hibáit egymással korrigálva megbízhatóbb középértéket kapunk.
        * **Kizárólag belföld:** A program felismeri Magyarország államhatárát, így a térképen és a számoknál csak hazai értékeket látsz.
        * **Helyszín-azonosítás:** Megmutatja, melyik nagyvárosunk környékén várható a legalacsonyabb és legmagasabb hőmérséklet.
        """)
        
    with tab2:
        st.write("""
        **Szakmai specifikáció:**
        1.  **Ensemble Súlyozás:** A rendszer az ECMWF (45%), GFS (30%) és ICON (25%) modellek kimeneteit súlyozza.
        2.  **Geospatialis Szűrés:** A `Shapely` könyvtár segítségével végzünk pont-a-poligonban (PIP) tesztet a rácsháló elemein.
        3.  **Adatfeldolgozás:** Az API lekérdezések 15-ös csoportokban (chunking) futnak a JSON stabilitás érdekében.
        """)
        
        # Modell súlyok vizualizálása
        w_df = pd.DataFrame({"Modell": ["ECMWF", "GFS", "ICON"], "Súly (%)": [45, 30, 25]})
        fig_w = px.pie(w_df, values='Súly (%)', names='Modell', hole=0.4, 
                       color_discrete_sequence=px.colors.sequential.Teal)
        fig_w.update_layout(height=180, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_w, use_container_width=True)

st.divider()

# OLDALSÁV
if st.sidebar.button("Hard Reset (Adatok frissítése)"):
    st.cache_data.clear()
    st.rerun()

target_date = st.sidebar.date_input("Válassz dátumot", datetime.now() + timedelta(days=1))

with st.spinner('Adatok elemzése...'):
    df = FETCH_FINAL_DATA(target_date)
    if not df.empty:
        # Szélsőértékek és városok
        min_row, max_row = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        min_city, max_city = find_nearest_city(min_row['lat'], min_row['lon']), find_nearest_city(max_row['lat'], max_row['lon'])

        c1, c2 = st.columns(2)
        c1.metric("Országos MIN", f"{round(min_row['min'], 1)} °C", f"({min_city} környéke)")
        c2.metric("Országos MAX", f"{round(max_row['max'], 1)} °C", f"({max_city} környéke)")
        
        m1, m2 = st.columns(2)
        def draw_map(data, col, colors, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=col, color_continuous_scale=colors, 
                                    zoom=6.1, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', 
                                           line=dict(width=3, color='black'), showlegend=False))
            fig.update_traces(marker=dict(size=18, opacity=0.9))
            fig.update_layout(title=title, margin={"r":0,"t":40,"l":0,"b":0})
            return fig

        m1.plotly_chart(draw_map(df, "min", "Viridis", "Súlyozott Minimumok"), use_container_width=True)
        m2.plotly_chart(draw_map(df, "max", "Reds", "Súlyozott Maximumok"), use_container_width=True)
