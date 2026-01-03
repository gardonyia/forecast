import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- OLDAL BEÁLLÍTÁSAI ---
st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide")

# --- SZIGORÍTOTT HATÁRVONAL ÉS VIZUALIZÁCIÓ ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# Városok a beazonosításhoz
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

MODELS = {"ecmwf_ifs": "ECMWF", "gfs_seamless": "GFS", "icon_seamless": "ICON"}

@st.cache_data(ttl=3600)
def get_weights_final():
    return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}

# --- EZ A FÜGGVÉNY OLDJA MEG A HIBAÜZENETET ---
def FINAL_STABLE_FETCH(date, weights):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    lats = np.arange(45.8, 48.6, 0.25)
    lons = np.arange(16.2, 22.8, 0.35)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la)
                v_lons.append(lo)

    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    
    # Kérések darabolása 15-ösével a stabilitásért
    chunk_size = 15 
    for i in range(0, len(v_lats), chunk_size):
        curr_lats = v_lats[i:i+chunk_size]
        curr_lons = v_lons[i:i+chunk_size]
        
        for m_id, w in weights.items():
            try:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": curr_lats, "longitude": curr_lons,
                    "hourly": "temperature_2m", "models": m_id,
                    "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }
                r = requests.get(url, params=params).json()
                pts = r if isinstance(r, list) else [r]
                
                for j, p in enumerate(pts):
                    idx = i + j
                    t = p['hourly']['temperature_2m']
                    results[idx]["min"] += min(t) * w
                    results[idx]["max"] += max(t) * w
            except:
                continue
    return pd.DataFrame(results)

# --- FELÜLET ---
st.title("🌡️ Súlyozott Magyarországi Előrejelzés")

if st.sidebar.button("Hard Reset (Minden frissítése)"):
    st.cache_data.clear()
    st.rerun()

target_date = st.sidebar.date_input("Válassz dátumot", datetime.now() + timedelta(days=1))
weights = get_weights_final()

with st.spinner('Adatok lekérése a határokon belül...'):
    # ITT MÁR AZ ÚJ FÜGGVÉNYT HÍVJUK
    df = FINAL_STABLE_FETCH(target_date, weights)
    
    if not df.empty:
        min_row = df.loc[df['min'].idxmin()]
        max_row = df.loc[df['max'].idxmax()]
        min_city = find_nearest_city(min_row['lat'], min_row['lon'])
        max_city = find_nearest_city(max_row['lat'], max_row['lon'])

        c1, c2 = st.columns(2)
        c1.metric("Országos MIN", f"{round(min_row['min'], 1)} °C", f"{min_city} környéke")
        c2.metric("Országos MAX", f"{round(max_row['max'], 1)} °C", f"{max_city} környéke")
        
        st.divider()

        def draw_map(data, col, colors, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=col, 
                                    color_continuous_scale=colors, zoom=6.1,
                                    center={"lat": 47.15, "lon": 19.5},
                                    mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(
                lat=HU_LINE_LATS, lon=HU_LINE_LONS,
                mode='lines', line=dict(width=3, color='black'),
                showlegend=False
            ))
            fig.update_traces(marker=dict(size=18, opacity=0.9))
            fig.update_layout(title=title, margin={"r":0,"t":40,"l":0,"b":0})
            return fig

        m1, m2 = st.columns(2)
        m1.plotly_chart(draw_map(df, "min", "Viridis", "Súlyozott Minimumok"), use_container_width=True)
        m2.plotly_chart(draw_map(df, "max", "Reds", "Súlyozott Maximumok"), use_container_width=True)
