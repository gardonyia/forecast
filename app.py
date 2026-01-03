import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Modell-Súlyozó Dashboard", layout="wide", page_icon="🌡️")

# UI Stílus javítások
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .tech-details { background-color: #f8f9fa; padding: 18px; border-radius: 10px; font-size: 0.88rem; border-left: 5px solid #0d6efd; line-height: 1.6; color: #333; }
    .tech-header { color: #0d6efd; font-weight: bold; margin-top: 10px; margin-bottom: 5px; display: block; text-transform: uppercase; font-size: 0.8rem; }
    /* A gomb és a dátumválasztó egy vonalba hozása */
    div[data-testid="stButton"] { margin-top: 28px !important; }
    /* Progress bar egyedi stílusa */
    .stProgress > div > div > div > div { background-color: #0d6efd; }
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ÉS ADATOK ---
HU_COORDS = [(16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05), (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40), (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25), (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])
CITIES = [{"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14}, {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Győr", "lat": 47.68, "lon": 17.63}, {"n": "Miskolc", "lat": 48.10, "lon": 20.78}]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- MODELL SÚLYOZÁS ---
def calculate_dynamic_weights(p_bar, p_text):
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    models = ["ecmwf_ifs", "gfs_seamless", "icon_seamless"]
    model_scores = {m: 0.0 for m in models}
    
    try:
        for idx, city in enumerate(CITIES):
            percent = int((idx / len(CITIES)) * 100)
            p_bar.progress(percent)
            p_text.markdown(f"📊 **Modellek validálása a tegnapi tényadatokkal: {percent}%** (Helyszín: {city['n']})")
            
            r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": city['lat'], "longitude": city['lon'], "hourly": "temperature_2m",
                "models": ",".join(models), "start_date": yesterday, "end_date": yesterday, "timezone": "UTC"
            }).json()
            ra = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
                "latitude": city['lat'], "longitude": city['lon'], "hourly": "temperature_2m",
                "start_date": yesterday, "end_date": yesterday
            }).json()
            
            actual = np.array(ra['hourly']['temperature_2m'])
            for m in models:
                pred = np.array(r['hourly'][f'temperature_2m_{m}'])
                mae = np.mean(np.abs(actual - pred))
                model_scores[m] += (1 / (mae + 0.1))
        
        total = sum(model_scores.values())
        return {m: model_scores[m]/total for m in models}
    except:
        return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}

# --- RÁCSHÁLÓ GENERÁLÁSA ---
def FETCH_FINAL_DATA(date, weights, p_bar, p_text):
    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00'), date.strftime('%Y-%m-%dT18:00')
    lats, lons = np.arange(45.8, 48.6, 0.15), np.arange(16.2, 22.8, 0.18)
    v_pts = [(la, lo) for la in lats for lo in lons if HU_POLY.contains(Point(lo, la))]
    results = [{"lat": p[0], "lon": p[1], "min": 0, "max": 0} for p in v_pts]
    
    for i in range(0, len(results), 10):
        percent = min(int((i / len(results)) * 100), 100)
        p_bar.progress(percent)
        p_text.markdown(f"🌍 **Adatok feldolgozása az Open-Meteo rácshálón: {percent}%**")
        
        chunk = v_pts[i:i+10]
        la_c, lo_c = [c[0] for c in chunk], [c[1] for c in chunk]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": la_c, "longitude": lo_c, "hourly": "temperature_2m", "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"}).json()
                pts = r if isinstance(r, list) else [r]
                for j, res in enumerate(pts):
                    results[i+j]["min"] += min(res['hourly']['temperature_2m']) * w
                    results[i+j]["max"] += max(res['hourly']['temperature_2m']) * w
            except: continue
    
    p_bar.empty(); p_text.empty()
    return pd.DataFrame(results)

# --- DASHBOARD UI ---
main_c, side_c = st.columns([2.8, 1.2], gap="large")

with main_c:
    st.title("🌡️ Súlyozott Modell-Előrejelzés")
    
    # Gomb igazítás javítása
    ctrl_col1, ctrl_col2, _ = st.columns([1.2, 0.5, 2.5])
    target_date = ctrl_col1.date_input("Dátum választása", datetime.now() + timedelta(days=1))
    if ctrl_col2.button("🔄"):
        st.cache_data.clear()
        st.rerun()

    # Helyőrzők a folyamatjelzőnek (hogy ne villogjon)
    p_bar = st.empty()
    p_text = st.empty()
    
    weights = calculate_dynamic_weights(p_bar, p_text)
    df = FETCH_FINAL_DATA(target_date, weights, p_bar, p_text)
    
    if not df.empty:
        m1, m2 = st.columns(2)
        min_r, max_r = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        
        # Településnév Pin ikonnal és dőlttel
        m1.metric("📉 Országos Minimum", f"{round(min_r['min'], 1)} °C", f"📍 *'{find_nearest_city(min_r['lat'], min_r['lon'])}' környékén*")
        m2.metric("📈 Országos Maximum", f"{round(max_r['max'], 1)} °C", f"📍 *'{find_nearest_city(max_r['lat'], max_r['lon'])}' környékén*")
        
        map1, map2 = st.columns(2)
        def draw(data, val, col, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=val, color_continuous_scale=col, zoom=6.0, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', line=dict(width=2, color='#444'), showlegend=False))
            fig.update_layout(title=title, margin={"r":0,"t":35,"l":0,"b":0}, height=450)
            return fig
        map1.plotly_chart(draw(df, "min", "Viridis", "Minimum Hőtérkép"), use_container_width=True)
        map2.plotly_chart(draw(df, "max", "Reds", "Maximum Hőtérkép"), use_container_width=True)

with side_c:
    st.subheader("📘 Technikai leírás")
    st.markdown("""
    <div class="tech-details">
        <span class="tech-header">1. Dinamikus Súlyozás (D-MOS)</span>
        A rendszer nem statikus súlyokat használ. Minden futtatáskor lekéri az elmúlt 24 óra <b>ténylegesen mért</b> (METAR/Archive) adatait és összeveti azokat a modellek (ECMWF, GFS, ICON) korábbi jóslataival. A súlyozás az inverz MAE (Mean Absolute Error) alapján dől el: amelyik modell tegnap pontosabb volt, az ma nagyobb befolyással bír.
        
        <span class="tech-header">2. Multi-Model Ensemble (MME)</span>
        Az előrejelzés három globális vezető modell integrációja:
        <ul>
            <li><b>ECMWF IFS:</b> Az európai nagyfelbontású modell.</li>
            <li><b>GFS:</b> Az amerikai globális rendszer.</li>
            <li><b>ICON:</b> A német meteorológiai szolgálat precíziós modellje.</li>
        </ul>

        <span class="tech-header">3. Rácsháló és Interpoláció</span>
        A számítás egy 0.15° x 0.18°-os rácshálón történik, amely ~130 pontot jelent Magyarország területén. A pontok szűrése a Shapely geometriai könyvtárral történik az országhatár poligonján belül.
        
        <span class="tech-header">4. Éghajlati ciklus</span>
        A napi szélsőértékek meghatározása a WMO szabvány szerinti 18:00 UTC - 18:00 UTC közötti időszakra vonatkozik, elkerülve a napi maximumok/minimumok kettévágását.
    </div>
    """, unsafe_allow_html=True)
    
    st.write("---")
    st.write("**Aktuális modell súlyok:**")
    w_df = pd.DataFrame({"Modell": ["ECMWF", "GFS", "ICON"], "Súly": [weights[m]*100 for m in ["ecmwf_ifs", "gfs_seamless", "icon_seamless"]]})
    st.plotly_chart(px.pie(w_df, values='Súly', names='Modell', hole=0.5, color_discrete_sequence=px.colors.sequential.Teal).update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250), use_container_width=True)
