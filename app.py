import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- OLDAL KONFIGURÁCIÓ ---
st.set_page_config(page_title="Magyarországi Időjárás Súlyozó", layout="wide")

# --- SZIGORÚ ORSZÁGHATÁR (Geofencing) ---
HU_COORDS = [
    (16.1, 46.6), (16.2, 47.1), (16.5, 47.5), (17.1, 48.0), (18.1, 48.1), 
    (18.8, 48.1), (19.2, 48.3), (19.8, 48.6), (20.9, 48.6), (22.0, 48.6), 
    (22.8, 48.4), (22.9, 48.0), (22.5, 47.4), (21.6, 46.7), (21.3, 46.2), 
    (20.5, 46.1), (19.4, 46.1), (18.8, 45.8), (17.5, 45.8), (16.6, 46.3), (16.1, 46.5)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS = [c[1] for c in HU_COORDS] + [HU_COORDS[0][1]]
HU_LINE_LONS = [c[0] for c in HU_COORDS] + [HU_COORDS[0][0]]

# Helyszín azonosító adatbázis
CITIES = [
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Sopron", "lat": 47.68, "lon": 16.59}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"name": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Nagykanizsa", "lat": 46.45, "lon": 17.00},
    {"n": "Siófok", "lat": 46.90, "lon": 18.05}, {"n": "Kecskemét", "lat": 46.90, "lon": 19.69},
    {"n": "Békéscsaba", "lat": 46.68, "lon": 21.09}, {"n": "Eger", "lat": 47.90, "lon": 20.37},
    {"n": "Szolnok", "lat": 47.17, "lon": 20.18}, {"n": "Tatabánya", "lat": 47.56, "lon": 18.41},
    {"n": "Záhony", "lat": 48.41, "lon": 22.17}, {"n": "Baja", "lat": 46.18, "lon": 18.95}
]

def find_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

MODELS = {"ecmwf_ifs": "ECMWF", "gfs_seamless": "GFS", "icon_seamless": "ICON"}

@st.cache_data(ttl=3600)
def get_weights_v2():
    # Fix súlyok a gyors teszteléshez, amíg a cache ürül
    return {"ecmwf_ifs": 0.4, "gfs_seamless": 0.3, "icon_seamless": 0.3}

def fetch_data_v2(date, weights):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    # Szigorú rács generálás
    lats = np.arange(45.8, 48.6, 0.22)
    lons = np.arange(16.1, 22.8, 0.3)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la)
                v_lons.append(lo)

    results = []
    for m_id, w in weights.items():
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": v_lats, "longitude": v_lons, "hourly": "temperature_2m",
            "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
        }).json()
        pts = r if isinstance(r, list) else [r]
        for i, p in enumerate(pts):
            temps = p['hourly']['temperature_2m']
            if len(results) <= i:
                results.append({"lat": v_lats[i], "lon": v_lons[i], "min": 0, "max": 0})
            results[i]["min"] += min(temps) * w
            results[i]["max"] += max(temps) * w
    return pd.DataFrame(results)

# --- MEGJELENÍTÉS ---
st.header("🌡️ Magyarországi Modell-Súlyozott Előrejelzés")

# KÉTSZERI KATTINTÁS ELKERÜLÉSE: Cache ürítő gomb
if st.sidebar.button("Minden adat frissítése (Hard Reset)"):
    st.cache_data.clear()
    st.rerun()

target_date = st.sidebar.date_input("Előrejelzés napja", datetime.now() + timedelta(days=1))
weights = get_weights_v2()

with st.spinner('Belföldi adatok elemzése...'):
    df = fetch_data_v2(target_date, weights)
    
    if not df.empty:
        # Helyszín azonosítás
        min_idx = df['min'].idxmin()
        max_idx = df['max'].idxmax()
        
        min_val, max_val = df.loc[min_idx, 'min'], df.loc[max_idx, 'max']
        min_loc = find_city(df.loc[min_idx, 'lat'], df.loc[min_idx, 'lon'])
        max_loc = find_city(df.loc[max_idx, 'lat'], df.loc[max_idx, 'lon'])

        col1, col2 = st.columns(2)
        col1.metric("Belföldi MIN", f"{round(min_val, 1)} °C", help=f"Helyszín: {min_loc} környéke")
        col2.metric("Belföldi MAX", f"{round(max_val, 1)} °C", help=f"Helyszín: {max_loc} környéke")
        
        st.info(f"📍 **Legalacsonyabb:** {min_loc} környéke | **Legmagasabb:** {max_loc} környéke")

        st.divider()
        m1, m2 = st.columns(2)
        
        # Térkép generáló függvény
        def draw_map(data, col, colors):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=col, 
                                    color_continuous_scale=colors, zoom=6.1, 
                                    center={"lat": 47.15, "lon": 19.5},
                                    mapbox_style="carto-positron")
            # FEKETE HATÁRVONAL RAJZOLÁSA
            fig.add_trace(go.Scattermapbox(
                lat=HU_LINE_LATS, lon=HU_LINE_LONS,
                mode='lines', line=dict(width=3, color='black'),
                name='Országhatár', showlegend=False
            ))
            fig.update_traces(marker=dict(size=16, opacity=0.85))
            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            return fig

        m1.plotly_chart(draw_map(df, "min", "Viridis"), use_container_width=True)
        m2.plotly_chart(draw_map(df, "max", "Reds"), use_container_width=True)

    else:
        st.error("Nincs megjeleníthető belföldi adat.")
