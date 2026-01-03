import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide", page_icon="🌡️")

# --- SZIGORÚ ORSZÁGHATÁR POLIGON ---
# Ez a koordináta-sorozat biztosítja, hogy Ausztria, Szlovénia, Horvátország, 
# Szerbia, Románia, Ukrajna és Szlovákia pontjai kiessenek.
HU_BOUNDARY = Polygon([
    (16.1, 46.6), (16.2, 47.1), (16.5, 47.5), (17.1, 48.0), (18.1, 48.1), 
    (18.8, 48.1), (19.2, 48.3), (19.8, 48.6), (20.9, 48.6), (22.0, 48.6), 
    (22.8, 48.4), (22.9, 48.0), (22.5, 47.4), (21.6, 46.7), (21.3, 46.2), 
    (20.5, 46.1), (19.4, 46.1), (18.8, 45.8), (17.5, 45.8), (16.6, 46.3), (16.1, 46.5)
])

MODELS = {"ecmwf_ifs": "ECMWF", "gfs_seamless": "GFS", "icon_seamless": "ICON"}

def is_in_hungary(lat, lon):
    """Csak akkor igaz, ha a pont Magyarországon belül van."""
    return HU_BOUNDARY.contains(Point(lon, lat))

@st.cache_data(ttl=86400)
def calculate_historical_weights():
    # Referencia pont: Budapest
    ref_lat, ref_lon = 47.49, 19.04
    end_date = (datetime.now() - timedelta(days=2)).date()
    start_date = end_date - timedelta(days=30)
    
    weights = {}
    try:
        # Tényleges archív adatok
        obs = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": ref_lat, "longitude": ref_lon, "start_date": start_date, "end_date": end_date,
            "daily": "temperature_2m_max", "timezone": "UTC"
        }).json()['daily']['temperature_2m_max']

        errors = {}
        for m_id in MODELS.keys():
            fc = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": ref_lat, "longitude": ref_lon, "start_date": start_date, "end_date": end_date,
                "models": m_id, "daily": "temperature_2m_max", "timezone": "UTC"
            }).json()['daily']['temperature_2m_max']
            
            mse = np.mean([(f - a)**2 for f, a in zip(fc, obs) if f is not None and a is not None])
            errors[m_id] = max(mse, 0.1)

        inv_sum = sum(1.0 / e for e in errors.values())
        for m_id in MODELS.keys():
            weights[m_id] = (1.0 / errors[m_id]) / inv_sum
    except:
        return {m: 0.33 for m in MODELS}
    return weights

def get_grid_forecast(date, weights):
    t_start = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_end = date.strftime('%Y-%m-%dT18:00')
    
    # Sűrűbb rács a határmenti pontosságért
    lats_grid = np.arange(45.7, 48.7, 0.2)
    lons_grid = np.arange(16.0, 23.0, 0.3)
    
    valid_lats, valid_lons = [], []
    for lat in lats_grid:
        for lon in lons_grid:
            if is_in_hungary(lat, lon):
                valid_lats.append(lat)
                valid_lons.append(lon)

    if not valid_lats: return pd.DataFrame()

    grid_data = []
    # Batch lekérdezés a sebességért
    for m_id, weight in weights.items():
        res = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": valid_lats, "longitude": valid_lons, 
            "hourly": "temperature_2m", "models": m_id, 
            "start_hour": t_start, "end_hour": t_end, "timezone": "UTC"
        }).json()
        
        points = res if isinstance(res, list) else [res]
        for i, p in enumerate(points):
            t = p['hourly']['temperature_2m']
            if len(grid_data) <= i:
                grid_data.append({"lat": valid_lats[i], "lon": valid_lons[i], "Tmin": 0, "Tmax": 0})
            grid_data[i]["Tmin"] += min(t) * weight
            grid_data[i]["Tmax"] += max(t) * weight
            
    return pd.DataFrame(grid_data)

# --- UI ---
st.title("🌡️ Súlyozott Magyarországi Előrejelzés")

with st.expander("🛡️ Határvédelmi és Módszertani adatok"):
    st.write("""
    Ez a modul garantálja, hogy kizárólag Magyarország területéről származó adatok kerüljenek feldolgozásra:
    1. **Geofencing:** Minden rácspontot egy matematikai poligon (országhatár) ellenőriz.
    2. **Kizárás:** Ausztria, Szlovákia, Ukrajna, Románia, Szerbia, Horvátország és Szlovénia minden adata automatikusan törlődik a számítás előtt.
    3. **Szélsőértékek:** Az alább látható MIN/MAX értékek már a szűrt belföldi adatbázisból készülnek.
    """)

weights = calculate_historical_weights()
target_date = st.sidebar.date_input("Dátum", datetime.now() + timedelta(days=1))

with st.spinner('Belföldi adatok elemzése...'):
    df_grid = get_grid_forecast(target_date, weights)
    
    if not df_grid.empty:
        # ITT TÖRTÉNIK A SZIGORÚ SZÁMÍTÁS
        abs_min = df_grid['Tmin'].min()
        abs_max = df_grid['Tmax'].max()

        c1, c2 = st.columns(2)
        c1.metric("Belföldi Abszolút MIN", f"{round(abs_min, 1)} °C")
        c2.metric("Belföldi Abszolút MAX", f"{round(abs_max, 1)} °C")

        st.subheader("Belföldi területi eloszlás")
        m1, m2 = st.columns(2)
        
        # A vizualizáció csak a belföldi pontokat rajzolja ki (scatter)
        # Nincs elmosódás, nincs "átlógás"
        common_map = dict(mapbox_style="carto-positron", center=dict(lat=47.15, lon=19.5), zoom=6.2, opacity=0.8)

        with m1:
            st.write("❄️ **Minimum hőmérsékletek**")
            fig1 = px.scatter_mapbox(df_grid, lat="lat", lon="lon", color="Tmin", 
                                     color_continuous_scale="Viridis", **common_map)
            fig1.update_traces(marker=dict(size=15))
            st.plotly_chart(fig1, use_container_width=True)

        with m2:
            st.write("☀️ **Maximum hőmérsékletek**")
            fig2 = px.scatter_mapbox(df_grid, lat="lat", lon="lon", color="Tmax", 
                                     color_continuous_scale="Reds", **common_map)
            fig2.update_traces(marker=dict(size=15))
            st.plotly_chart(fig2, use_container_width=True)
