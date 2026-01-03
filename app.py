import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- OLDAL BEÁLLÍTÁSA ---
st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide", page_icon="🌡️")

# --- MAGYARORSZÁG HATÁRAI (POLIGON SZŰRÉSHEZ) ---
# Egy egyszerűsített körvonal, amely lefedi az országot
HU_BOUNDARY = Polygon([
    (16.1, 46.8), (16.5, 47.3), (17.2, 48.0), (18.8, 48.1), (19.5, 48.6), 
    (21.0, 48.6), (22.2, 48.4), (22.9, 47.9), (22.7, 47.0), (21.5, 46.1), 
    (20.2, 46.0), (18.8, 45.8), (17.2, 45.8), (16.1, 46.5)
])

MODELS = {
    "ecmwf_ifs": "ECMWF (Európai)",
    "gfs_seamless": "GFS (Amerikai)",
    "icon_seamless": "ICON (Német)"
}

def is_in_hungary(lat, lon):
    """Ellenőrzi, hogy a koordináta Magyarországon belül van-e."""
    return HU_BOUNDARY.contains(Point(lon, lat))

# --- HISTORIKUS SÚLYOZÁS ---
@st.cache_data(ttl=86400)
def calculate_historical_weights():
    ref_lat, ref_lon = 47.5, 19.0 # Budapest referencia
    end_date = (datetime.now() - timedelta(days=2)).date()
    start_date = end_date - timedelta(days=30)
    
    weights = {}
    errors = {}
    try:
        obs_res = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": ref_lat, "longitude": ref_lon,
            "start_date": start_date, "end_date": end_date,
            "daily": "temperature_2m_max", "timezone": "UTC"
        }).json()
        actuals = obs_res['daily']['temperature_2m_max']

        for m_id in MODELS.keys():
            fc_res = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": ref_lat, "longitude": ref_lon,
                "start_date": start_date, "end_date": end_date,
                "models": m_id, "daily": "temperature_2m_max", "timezone": "UTC"
            }).json()
            fcs = fc_res['daily']['temperature_2m_max']
            mse = np.mean([(f - a)**2 for f, a in zip(fcs, actuals) if f is not None and a is not None])
            errors[m_id] = max(mse, 0.1)

        inv_sum = sum(1.0 / e for e in errors.values())
        for m_id in MODELS.keys():
            weights[m_id] = (1.0 / errors[m_id]) / inv_sum
    except:
        return {m: 0.33 for m in MODELS}, {m: 0 for m in MODELS}
        
    return weights, errors

# --- ELŐREJELZÉS LEKÉRÉSE RÁCSRA ---
def get_grid_forecast(date, weights):
    t_start = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_end = date.strftime('%Y-%m-%dT18:00')
    
    # Sűrített rácsháló a határszűréshez
    lats_grid = np.arange(45.7, 48.7, 0.4)
    lons_grid = np.arange(16.0, 23.0, 0.6)
    
    grid_data = []
    for lat in lats_grid:
        for lon in lons_grid:
            if is_in_hungary(lat, lon): # CSAK MAGYAR PONTOK
                p_min, p_max = 0, 0
                for m_id, weight in weights.items():
                    res = requests.get("https://api.open-meteo.com/v1/forecast", params={
                        "latitude": lat, "longitude": lon, "hourly": "temperature_2m",
                        "models": m_id, "start_hour": t_start, "end_hour": t_end, "timezone": "UTC"
                    }).json()
                    temps = res['hourly']['temperature_2m']
                    p_min += min(temps) * weight
                    p_max += max(temps) * weight
                
                grid_data.append({"lat": lat, "lon": lon, "Tmin": p_min, "Tmax": p_max})
    return pd.DataFrame(grid_data)

# --- UI FELÜLET ---
st.title("🌡️ Országos Modell-Súlyozott Előrejelző")

with st.expander("ℹ️ Módszertani leírás (Hogyan működik?)"):
    st.markdown("""
    * **Területi szűrés:** A rendszer csak a Magyarország közigazgatási határain belüli rácspontokat vizsgálja.
    * **Dinamikus súlyozás:** Az elmúlt 30 nap mérési adatai alapján az a modell kap nagyobb prioritást, amelyik a legkisebb hibaszázalékkal dolgozott.
    * **18:00 - 18:00 UTC ablak:** A szélsőértékeket meteorológiai napra számoljuk, így a hajnali fagy és a nappali csúcsérték egy ciklusba esik.
    """)

weights, errors = calculate_historical_weights()
target_date = st.sidebar.date_input("Előrejelzés napja", datetime.now() + timedelta(days=1))

if st.sidebar.button("Gyorsítótár ürítése"):
    st.cache_data.clear()
    st.rerun()

# Számítás és Megjelenítés
with st.spinner('Országos rács elemzése (csak belföldi pontok)...'):
    df_grid = get_grid_forecast(target_date, weights)
    
    if not df_grid.empty:
        abs_min = df_grid['Tmin'].min()
        abs_max = df_grid['Tmax'].max()

        col1, col2, col3 = st.columns([1,1,2])
        col1.metric("Országos MIN", f"{round(abs_min, 1)} °C")
        col2.metric("Országos MAX", f"{round(abs_max, 1)} °C")
        
        with col3:
            st.write("**Aktuális súlyozás (30 napos MSE alapján):**")
            w_text = " | ".join([f"{MODELS[m].split(' ')[0]}: {round(w*100)}%" for m, w in weights.items()])
            st.caption(w_text)

        st.divider()

        st.subheader(f"Súlyozott hőtérkép: {target_date}")
        map_col1, map_col2 = st.columns(2)
        
        with map_col1:
            st.write("❄️ **Minimumok**")
            fig_min = px.density_mapbox(df_grid, lat='lat', lon='lon', z='Tmin', radius=45,
                                        center=dict(lat=47.1, lon=19.5), zoom=6,
                                        mapbox_style="carto-positron", color_continuous_scale="Viridis")
            st.plotly_chart(fig_min, use_container_width=True)

        with map_col2:
            st.write("☀️ **Maximumok**")
            fig_max = px.density_mapbox(df_grid, lat='lat', lon='lon', z='Tmax', radius=45,
                                        center=dict(lat=47.1, lon=19.5), zoom=6,
                                        mapbox_style="carto-positron", color_continuous_scale="Reds")
            st.plotly_chart(fig_max, use_container_width=True)
    else:
        st.error("Nem sikerült adatokat lekérni a rácshálóra.")
