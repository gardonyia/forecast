import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Modell-Súlyozó Dashboard", layout="wide", page_icon="🌡️")

# UI Fixek
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .tech-details { background-color: #f8f9fa; padding: 20px; border-radius: 10px; font-size: 0.9rem; border-left: 5px solid #0d6efd; color: #333; line-height: 1.6; }
    div[data-testid="stButton"] { padding-top: 25px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- TELEPÜLÉSLISTA (3155 pont) ---
@st.cache_data
def load_towns():
    url = "https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json"
    try:
        r = requests.get(url).json()
        return [{"n": d['name'], "lat": float(d['lat']), "lon": float(d['lng'])} for d in r]
    except:
        return [{"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Zabar", "lat": 48.15, "lon": 20.05}]

# --- VALIDÁCIÓ ÉS SÚLYOK ---
@st.cache_data(ttl=3600)
def get_weights():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    # Validációs pont: Budapest
    try:
        obs = requests.get(f"https://archive-api.open-meteo.com/v1/archive?latitude=47.49&longitude=19.04&start_date={yesterday}&end_date={yesterday}&hourly=temperature_2m").json()
        t_min, t_max = min(obs['hourly']['temperature_2m']), max(obs['hourly']['temperature_2m'])
        
        models = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
        val_data = []
        errors = []
        
        for m, w in models.items():
            fc = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude=47.49&longitude=19.04&start_date={yesterday}&end_date={yesterday}&hourly=temperature_2m&models={m}").json()
            p_min, p_max = min(fc['hourly']['temperature_2m']), max(fc['hourly']['temperature_2m'])
            err = (abs(t_min - p_min) + abs(t_max - p_max)) / 2
            errors.append(max(0.1, err))
            val_data.append({"Modell": m.upper(), "Jósolt": f"{p_min}/{p_max}", "Hiba": round(err, 2)})
            
        inv_err = [1/e for e in errors]
        final_w = {m: ie/sum(inv_err) for m, ie in zip(models.keys(), inv_err)}
        return final_w, pd.DataFrame(val_data), f"{t_min} / {t_max} °C"
    except:
        return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}, None, "N/A"

# --- ADATLEKÉRÉS ---
def FETCH_DATA(date, weights, towns, p_bar):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_e = date.strftime('%Y-%m-%d')
    results = []
    
    # Batch processing
    for i in range(0, len(towns), 100):
        p_bar.progress(min(i / len(towns), 1.0))
        batch = towns[i:i+100]
        lats = ",".join([str(t['lat']) for t in batch])
        lons = ",".join([str(t['lon']) for t in batch])
        
        batch_df = pd.DataFrame([{"n": t['n'], "lat": t['lat'], "lon": t['lon'], "min": 0.0, "max": 0.0} for t in batch])
        
        for m, w in weights.items():
            try:
                r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&start_date={t_s}&end_date={t_e}&hourly=temperature_2m&models={m}").json()
                res_list = r if isinstance(r, list) else [r]
                for idx, res in enumerate(res_list):
                    temps = res['hourly']['temperature_2m']
                    batch_df.at[idx, "min"] += min(temps) * w
                    batch_df.at[idx, "max"] += max(temps) * w
            except: continue
        results.append(batch_df)
    
    p_bar.empty()
    return pd.concat(results)

# --- DASHBOARD ---
main_c, side_c = st.columns([2.5, 1.5], gap="large")

with main_c:
    st.title("🌡️ Modell-Súlyozó Dashboard")
    c1, c2, _ = st.columns([1.2, 0.4, 2.4])
    target_date = c1.date_input("Dátum választása", datetime.now() + timedelta(days=1))
    
    weights, val_df, val_obs = get_weights()
    town_list = load_towns()
    
    p_bar = st.progress(0)
    df = FETCH_DATA(target_date, weights, town_list, p_bar)
    
    if not df.empty and df['min'].sum() != 0:
        col_min, col_max = st.columns(2)
        min_p = df.loc[df['min'].idxmin()]
        max_p = df.loc[df['max'].idxmax()]
        
        col_min.metric("📉 Országos Minimum", f"{round(min_p['min'], 1)} °C")
        col_min.markdown(f"📍 *{min_p['n']} környékén*")
        
        col_max.metric("📈 Országos Maximum", f"{round(max_p['max'], 1)} °C")
        col_max.markdown(f"📍 *{max_p['n']} környékén*")
        
        st.write("---")
        m_col1, m_col2 = st.columns(2)
        
        # Térkép beállítások a teljes lefedettséghez
        map_style = {"margin":{"r":0,"t":30,"l":0,"b":0}, "mapbox":{"zoom":6, "center":{"lat":47.15, "lon":19.5}}}
        
        fig_min = px.scatter_mapbox(df, lat="lat", lon="lon", color="min", hover_name="n", 
                                    color_continuous_scale="Viridis", mapbox_style="carto-positron", title="Minimum Hőtérkép")
        fig_min.update_traces(marker={"size": 12, "opacity": 0.7})
        fig_min.update_layout(map_style)
        m_col1.plotly_chart(fig_min, use_container_width=True)
        
        fig_max = px.scatter_mapbox(df, lat="lat", lon="lon", color="max", hover_name="n", 
                                    color_continuous_scale="Reds", mapbox_style="carto-positron", title="Maximum Hőtérkép")
        fig_max.update_traces(marker={"size": 12, "opacity": 0.7})
        fig_max.update_layout(map_style)
        m_col2.plotly_chart(fig_max, use_container_width=True)

with side_c:
    st.header("⚙️ Rendszerlogika")
    
    with st.expander("📊 1. Dinamikus Súlyozás (D-MOS)", expanded=True):
        if val_df is not None:
            st.write(f"Tegnapi valós bázisadatok (Budapest): **{val_obs}**")
            st.table(val_df)
        st.write("Az inverz MAE (Mean Absolute Error) alapján a pontosabb modellek nagyobb súlyt kapnak.")

    with st.expander("🏗️ 2. Adatfeldolgozási folyamat"):
        st.write("""
        - **3155 település:** Minden magyarországi lakott helyszín szerepel az elemzésben.
        - **Batch Fetching:** Az adatokat 100-as csomagokban kérjük le a stabil API kapcsolat érdekében.
        - **MME (Multi-Model Ensemble):** ECMWF (45%), GFS (30%) és ICON (25%) modellek dinamikusan korrigált integrációja.
        """)

    with st.expander("🗺️ 3. Vizualizáció"):
        st.write("A pontok méretét és áttetszőségét úgy optimalizáltuk, hogy az ország teljes területét lefedő, folytonos hőtérképet alkossanak.")

    st.write("---")
    st.write("**Mai súlyeloszlás:**")
    st.plotly_chart(px.pie(values=list(weights.values()), names=["ECMWF", "GFS", "ICON"], hole=0.5).update_layout(margin=dict(t=0, b=0, l=0, r=0), height=200))
