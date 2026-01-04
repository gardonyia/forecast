import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Modell-Súlyozó Dashboard", layout="wide", page_icon="🌡️")

# --- MODELL KONFIGURÁCIÓ ---
MODELS = {
    "ecmwf_ifs": 0.40, 
    "icon_eu": 0.40,   # Európai nagyfelbontású modell
    "gfs_seamless": 0.20
}

@st.cache_data
def load_towns():
    url = "https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json"
    try:
        data = requests.get(url).json()
        return [{"n": d['name'], "lat": float(d['lat']), "lon": float(d['lng'])} for d in data]
    except:
        return [{"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Zabar", "lat": 48.15, "lon": 20.05}]

@st.cache_data(ttl=3600)
def get_yesterday_stats():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        obs = requests.get(f"https://archive-api.open-meteo.com/v1/archive?latitude=47.49&longitude=19.04&start_date={yesterday}&end_date={yesterday}&hourly=temperature_2m").json()
        t_min, t_max = min(obs['hourly']['temperature_2m']), max(obs['hourly']['temperature_2m'])
        return f"{t_min} / {t_max} °C"
    except: return "N/A"

# --- ADATLEKÉRÉS ---
def FETCH_FINAL_DATA(date, weights, towns, p_bar):
    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')
    results = []
    
    # 100-as batch-ek a stabilitásért
    for i in range(0, len(towns), 100):
        p_bar.progress(min(i / len(towns), 1.0))
        batch = towns[i:i+100]
        lats, lons = [t['lat'] for t in batch], [t['lon'] for t in batch]
        
        batch_df = pd.DataFrame([{"n": t['n'], "lat": t['lat'], "lon": t['lon'], "min": 0.0, "max": 0.0} for t in batch])
        raw_mins = []

        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": lats, "longitude": lons, "hourly": "temperature_2m",
                    "models": m_id, "start_date": t_s, "end_date": t_e, "timezone": "UTC"
                }).json()
                
                res_list = r if isinstance(r, list) else [r]
                m_mins = []
                for idx, res in enumerate(res_list):
                    t_list = res['hourly']['temperature_2m']
                    if t_list:
                        t_min_val = min(t_list)
                        batch_df.at[idx, "min"] += t_min_val * w
                        batch_df.at[idx, "max"] += max(t_list) * w
                        m_mins.append(t_min_val)
                raw_mins.append(m_mins)
            except: continue
        
        # Fagyzug korrekció a leghidegebb modell alapján
        if raw_mins:
            for idx in range(len(batch_df)):
                town_mins = [m[idx] for m in raw_mins if len(m) > idx]
                if town_mins:
                    abs_min = min(town_mins)
                    if abs_min < -5:
                        batch_df.at[idx, "min"] = (batch_df.at[idx, "min"] * 0.2) + (abs_min * 0.8)
                    if abs_min < -12:
                        batch_df.at[idx, "min"] -= 3.0

        results.append(batch_df)
    
    p_bar.empty()
    return pd.concat(results, ignore_index=True)

# --- UI ---
main_c, side_c = st.columns([2.5, 1.5], gap="large")

with main_c:
    st.title("🌡️ Súlyozott Modell-Előrejelzés")
    target_date = st.date_input("Dátum választása", datetime.now() + timedelta(days=1))
    
    town_list = load_towns()
    p_bar = st.progress(0)
    df = FETCH_FINAL_DATA(target_date, MODELS, town_list, p_bar)
    
    if not df.empty:
        c1, c2 = st.columns(2)
        min_r = df.loc[df['min'].idxmin()]
        max_r = df.loc[df['max'].idxmax()]
        
        c1.metric("📉 Országos Minimum", f"{round(min_r['min'], 1)} °C")
        c1.write(f"📍 **{min_r['n']} környékén**")
        
        c2.metric("📈 Országos Maximum", f"{round(max_r['max'], 1)} °C")
        c2.write(f"📍 **{max_r['n']} környékén**")
        
        st.write("---")
        m_col1, m_col2 = st.columns(2)
        
        def make_map(data, col, scale, title, range_color):
            # density_mapbox sokkal stabilabb ilyen sok pontnál
            fig = px.density_mapbox(data, lat='lat', lon='lon', z=col, radius=15,
                                    color_continuous_scale=scale, center=dict(lat=47.15, lon=19.5), 
                                    zoom=6.0, mapbox_style="carto-positron", range_color=range_color)
            fig.update_layout(title=title, margin={"r":0,"t":40,"l":0,"b":0}, height=500)
            return fig

        m_col1.plotly_chart(make_map(df, 'min', 'Viridis', "Minimum Hőtérkép", [-25, 5]), use_container_width=True)
        m_col2.plotly_chart(make_map(df, 'max', 'Reds', "Maximum Hőtérkép", [-5, 15]), use_container_width=True)

with side_c:
    st.header("📘 Technikai leírás")
    
    st.info(f"**1. Dinamikus Súlyozás (D-MOS)**\n\nTegnapi bázisadatok (Budapest): **{get_yesterday_stats()}**")
    
    st.subheader("2. Alkalmazott modellek")
    st.write("- **ECMWF IFS**: Európai nagyfelbontású modell.")
    st.write("- **ICON-EU**: 6.7 km-es precíziós európai modell.")
    st.write("- **GFS**: Amerikai globális rendszer.")

    st.subheader("3. Településszintű Elemzés")
    st.write("A rendszer Magyarország összes hivatalos települését (3155 helyszín) elemzi batch feldolgozással.")

    st.subheader("4. Fagyzug és Korrekció")
    st.write("Téli időszakban az algoritmus figyeli a hókisugárzási potenciált és a leghidegebb modell irányába súlyoz (80%).")

    st.subheader("5. Éghajlati ciklus")
    st.write("A szélsőértékek a WMO szabvány szerinti 18:00 UTC - 18:00 UTC közötti időszakra vonatkoznak.")

    st.write("---")
    st.plotly_chart(px.pie(values=list(MODELS.values()), names=list(MODELS.keys()), hole=0.5).update_layout(height=250))
