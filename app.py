import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Dinamikus Modell-Súlyozó", layout="wide", page_icon="🌡️")

# UI Stílus
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .tech-details { background-color: #f8f9fa; padding: 15px; border-radius: 10px; font-size: 0.82rem; line-height: 1.5; border-left: 4px solid #0d6efd; margin-bottom: 20px; }
    .tech-header { color: #0d6efd; font-weight: bold; margin-top: 10px; margin-bottom: 5px; display: block; }
    div[data-testid="stButton"] { margin-top: 28px; }
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ---
HU_COORDS = [(16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05), (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40), (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25), (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])
CITIES = [{"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14}, {"n": "Pécs", "lat": 46.07, "lon": 18.23}]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- DINAMIKUS SÚLYOZÁS VALIDÁCIÓVAL ÉS PROGRESS BAR-RAL ---
def calculate_dynamic_weights_with_progress():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    models = ["ecmwf_ifs", "gfs_seamless", "icon_seamless"]
    model_scores = {m: 0.0 for m in models}
    
    prog_w = st.progress(0)
    stat_w = st.empty()
    total_steps = len(CITIES)
    
    try:
        for idx, city in enumerate(CITIES):
            percent = int(((idx) / total_steps) * 100)
            prog_w.progress(percent)
            stat_w.markdown(f"**1. FÁZIS: Modellek tegnapi hibájának elemzése: {percent}% ({city['n']})**")
            
            r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": city['lat'], "longitude": city['lon'],
                "hourly": "temperature_2m", "models": ",".join(models),
                "start_date": yesterday, "end_date": yesterday, "timezone": "UTC"
            }).json()
            
            ra = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
                "latitude": city['lat'], "longitude": city['lon'],
                "hourly": "temperature_2m", "start_date": yesterday, "end_date": yesterday
            }).json()
            
            actual = np.array(ra['hourly']['temperature_2m'])
            
            for m in models:
                pred = np.array(r['hourly'][f'temperature_2m_{m}'])
                mae = np.mean(np.abs(actual - pred))
                model_scores[m] += (1 / (mae + 0.1))
        
        prog_w.progress(100)
        total_score = sum(model_scores.values())
        final_weights = {m: model_scores[m]/total_score for m in models}
        
        prog_w.empty()
        stat_w.empty()
        return final_weights
    except:
        prog_w.empty()
        stat_w.empty()
        return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}

# --- ADATLEKÉRÉS SZÁZALÉKOSAN ---
@st.cache_data(ttl=3600)
def FETCH_FINAL_DATA(date, weights):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    lats, lons = np.arange(45.8, 48.6, 0.15), np.arange(16.2, 22.8, 0.18)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)): v_lats.append(la); v_lons.append(lo)

    total_points = len(v_lats)
    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    
    prog = st.progress(0)
    stat = st.empty()
    
    chunk_size = 10
    for i in range(0, total_points, chunk_size):
        percent = min(int((i / total_points) * 100), 100)
        prog.progress(percent)
        stat.markdown(f"**2. FÁZIS: Súlyozott rácsháló generálása: {percent}%**")
        
        curr_la, curr_lo = v_lats[i:i+chunk_size], v_lons[i:i+chunk_size]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": curr_la, "longitude": curr_lo, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }, timeout=15).json()
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    if 'hourly' in p:
                        results[i+j]["min"] += min(p['hourly']['temperature_2m']) * w
                        results[i+j]["max"] += max(p['hourly']['temperature_2m']) * w
            except: continue
            
    prog.empty()
    stat.empty()
    return pd.DataFrame(results)

# --- DASHBOARD ---
main_c, side_c = st.columns([2.8, 1.2], gap="large")

with main_c:
    st.title("🌡️ Dinamikus Modell-Súlyozó")
    ctrl_col1, ctrl_col2 = st.columns([1.2, 2.8])
    target_date = ctrl_col1.date_input("Dátum választása", datetime.now() + timedelta(days=1))
    
    if ctrl_col2.button("🔄"):
        st.cache_data.clear()
        st.rerun()
    
    current_weights = calculate_dynamic_weights_with_progress()
    df = FETCH_FINAL_DATA(target_date, current_weights)
    
    if not df.empty:
        min_r, max_r = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        mc1, mc2 = st.columns(2)
        mc1.metric("📉 Országos Minimum", f"{round(min_r['min'], 1)} °C", f"{find_nearest_city(min_r['lat'], min_r['lon'])} környéke")
        mc2.metric("📈 Országos Maximum", f"{round(max_r['max'], 1)} °C", f"{find_nearest_city(max_r['lat'], max_r['lon'])} környéke")
        
        mapc1, mapc2 = st.columns(2)
        def draw_m(data, val, col, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=val, color_continuous_scale=col, zoom=6.0, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', line=dict(width=2, color='#444'), showlegend=False))
            fig.update_layout(title=title, margin={"r":0,"t":35,"l":0,"b":0}, height=450)
            return fig
        mapc1.plotly_chart(draw_m(df, "min", "Viridis", "Minimum Hőtérkép"), use_container_width=True)
        mapc2.plotly_chart(draw_m(df, "max", "Reds", "Maximum Hőtérkép"), use_container_width=True)

with side_c:
    st.subheader("📘 Technikai leírás")
    st.markdown("""
    <div class="tech-details">
        <span class="tech-header">1. Dinamikus Súlyozás (D-MOS)</span>
        A rendszer minden futtatáskor elvégzi a modellek <b>on-the-fly validációját</b>. Lekéri a tegnapi tényadatokat és a tegnapi jóslatokat 4 reprezentatív városban. A súlyozás alapja az inverz hibaarány ($1 / (MAE + 0.1)$), így az aktuálisan legpontosabb modell kapja a legnagyobb szerepet.
        
        <span class="tech-header">2. Százalékos Betöltési Fázisok</span>
        A transzparencia érdekében két külön folyamatjelző méri a haladást:
        <ul>
            <li><b>Validációs fázis:</b> A történeti hiba mérése városonként.</li>
            <li><b>Generálási fázis:</b> A rácsháló pontjainak kiszámítása.</li>
        </ul>

        <span class="tech-header">3. Rácsháló és Éghajlati Nap</span>
        A 15 km-es rácsháló és a 18:00 UTC-s éghajlati nap garantálja a nemzetközi meteorológiai szabványoknak való megfelelést.
    </div>
    """, unsafe_allow_html=True)
    
    st.write("---")
    st.write("**Aktuális dinamikus súlyok:**")
    w_df = pd.DataFrame({
        "Modell": ["ECMWF", "GFS", "ICON"], 
        "Súly": [current_weights["ecmwf_ifs"]*100, current_weights["gfs_seamless"]*100, current_weights["icon_seamless"]*100]
    })
    fig_p = px.pie(w_df, values='Súly', names='Modell', hole=0.5, color_discrete_sequence=px.colors.sequential.Teal)
    fig_p.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, showlegend=True, legend=dict(orientation="h", y=-0.1))
    st.plotly_chart(fig_p, use_container_width=True)
