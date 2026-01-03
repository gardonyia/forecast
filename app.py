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

# --- PONTOSÍTOTT MAGYARORSZÁG HATÁR POLIGON ---
# Ez a poligon szorosan körbezárja Magyarországot, kizárva minden szomszédos országot.
HU_BOUNDARY = Polygon([
    (16.1, 46.6), (16.2, 46.9), (16.5, 47.3), (17.1, 48.0), (18.0, 48.1), 
    (18.8, 48.1), (19.0, 48.3), (19.6, 48.6), (20.5, 48.6), (21.5, 48.6), 
    (22.1, 48.5), (22.8, 48.4), (22.9, 48.1), (22.7, 47.9), (22.4, 47.5), 
    (21.5, 46.8), (21.3, 46.2), (20.7, 46.1), (20.2, 46.1), (19.4, 46.1), 
    (18.8, 45.8), (18.1, 45.8), (17.5, 45.9), (16.8, 46.2), (16.1, 46.4)
])

MODELS = {
    "ecmwf_ifs": "ECMWF (Európai)",
    "gfs_seamless": "GFS (Amerikai)",
    "icon_seamless": "ICON (Német)"
}

def is_in_hungary(lat, lon):
    return HU_BOUNDARY.contains(Point(lon, lat))

# --- HISTORIKUS SÚLYOZÁS ---
@st.cache_data(ttl=86400)
def calculate_historical_weights():
    ref_lat, ref_lon = 47.5, 19.0 
    end_date = (datetime.now() - timedelta(days=2)).date()
    start_date = end_date - timedelta(days=30)
    
    weights = {}
    try:
        obs_res = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": ref_lat, "longitude": ref_lon,
            "start_date": start_date, "end_date": end_date,
            "daily": "temperature_2m_max", "timezone": "UTC"
        }).json()
        actuals = obs_res['daily']['temperature_2m_max']

        errors = {}
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

# --- ADATLEKÉRÉS ---
def get_grid_forecast(date, weights):
    t_start = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_end = date.strftime('%Y-%m-%dT18:00')
    
    # Sűrű rács a pontos határkövetéshez
    lats_grid = np.arange(45.7, 48.7, 0.25)
    lons_grid = np.arange(16.0, 23.0, 0.3)
    
    valid_lats, valid_lons = [], []
    for lat in lats_grid:
        for lon in lons_grid:
            if is_in_hungary(lat, lon):
                valid_lats.append(lat)
                valid_lons.append(lon)

    if not valid_lats: return pd.DataFrame()

    model_results = {m_id: [] for m_id in MODELS.keys()}
    for m_id in MODELS.keys():
        res = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": valid_lats, "longitude": valid_lons, 
            "hourly": "temperature_2m", "models": m_id, 
            "start_hour": t_start, "end_hour": t_end, "timezone": "UTC"
        }).json()
        
        for point in (res if isinstance(res, list) else [res]):
            temps = point['hourly']['temperature_2m']
            model_results[m_id].append({"min": min(temps), "max": max(temps)})

    grid_data = []
    for i in range(len(valid_lats)):
        p_min = sum(model_results[m_id][i]["min"] * weights[m_id] for m_id in MODELS.keys())
        p_max = sum(model_results[m_id][i]["max"] * weights[m_id] for m_id in MODELS.keys())
        grid_data.append({"lat": valid_lats[i], "lon": valid_lons[i], "Tmin": p_min, "Tmax": p_max})
        
    return pd.DataFrame(grid_data)

# --- UI ---
st.title("🌡️ Magyarországi Modell-Súlyozott Előrejelző")

with st.expander("ℹ️ Hogyan működik a határszűrés és a súlyozás?"):
    st.markdown("""
    * **Szigorú belföldi fókusz:** Minden rácspont átesik egy geometriai ellenőrzésen. Csak azokat a pontokat vesszük figyelembe, amelyek Magyarország államhatárán belül helyezkednek el.
    * **Vizuális pontosság:** A térkép csak a belföldi adatpontokat jeleníti meg, így elkerülhető, hogy a szomszédos országok (pl. Románia vagy Szlovákia) szélsőértékei torzítsák az országos statisztikát.
    * **Hiba alapú súlyozás:** Az elmúlt 30 nap mérései alapján a legpontosabb modell kapja a legnagyobb szerepet.
    """)

weights, errors = calculate_historical_weights()
target_date = st.sidebar.date_input("Válassz dátumot", datetime.now() + timedelta(days=1))

with st.spinner('Magyarországi rács generálása...'):
    df_grid = get_grid_forecast(target_date, weights)
    
    if not df_grid.empty:
        abs_min, abs_max = df_grid['Tmin'].min(), df_grid['Tmax'].max()

        c1, c2 = st.columns(2)
        c1.metric("Országos belföldi MIN", f"{round(abs_min, 1)} °C")
        col1, col2 = st.columns(2) # Külön sor a maximumhoz is ha kell
        c2.metric("Országos belföldi MAX", f"{round(abs_max, 1)} °C")

        st.divider()

        # TÉRKÉPEK
        st.subheader(f"Területi eloszlás: {target_date}")
        m1, m2 = st.columns(2)
        
        # Plotly beállítások a tiszta határokhoz
        map_args = dict(mapbox_style="carto-positron", center=dict(lat=47.1, lon=19.5), zoom=6.2)

        with m1:
            st.write("❄️ **Súlyozott Minimumok**")
            fig_min = px.scatter_mapbox(df_grid, lat='lat', lon='lon', color='Tmin', size_max=15,
                                        color_continuous_scale="Viridis", **map_args)
            fig_min.update_traces(marker={'size': 12, 'opacity': 0.8})
            st.plotly_chart(fig_min, use_container_width=True)

        with m2:
            st.write("☀️ **Súlyozott Maximumok**")
            fig_max = px.scatter_mapbox(df_grid, lat='lat', lon='lon', color='Tmax', size_max=15,
                                        color_continuous_scale="Reds", **map_args)
            fig_max.update_traces(marker={'size': 12, 'opacity': 0.8})
            st.plotly_chart(fig_max, use_container_width=True)
    else:
        st.error("Nincs megjeleníthető adat a magyar határokon belül.")
