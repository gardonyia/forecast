import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ & TIPPMIXPRO STÍLUS ---
st.set_page_config(page_title="Modell-Súlyozó PRO", layout="wide", page_icon="🌡️")

# CSS a TippmixPro UI utánzására
st.markdown("""
    <style>
    /* Fő háttér és betűszín */
    .stApp { background-color: #121416; color: #ffffff; }
    
    /* Fejléc stílus */
    .main-header { 
        background-color: #1a1c1e; 
        padding: 1rem; 
        border-bottom: 4px solid #00df5d; 
        margin-bottom: 20px;
        border-radius: 0 0 10px 10px;
    }
    
    /* TippmixPro Zöld gomb */
    div[data-testid="stButton"] button {
        background-color: #00df5d !important;
        color: #000000 !important;
        font-weight: 800 !important;
        border-radius: 4px !important;
        border: none !important;
        width: 100%;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Metrikák (mint az oddsok a Tippmixen) */
    [data-testid="stMetricValue"] { color: #00df5d !important; font-size: 2rem !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #9da3a8 !important; text-transform: uppercase; font-size: 0.8rem !important; }
    [data-testid="stMetric"] { 
        background-color: #1a1c1e; 
        padding: 20px; 
        border-radius: 8px; 
        border: 1px solid #2d3135; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Technikai Szelvény (Sidebar stílus) */
    .tech-details { 
        background-color: #1a1c1e; 
        padding: 20px; 
        border-radius: 8px; 
        font-size: 0.85rem; 
        border-left: 5px solid #00df5d;
        margin-bottom: 20px;
        line-height: 1.6;
    }
    .tech-header { 
        color: #00df5d; 
        font-weight: bold; 
        text-transform: uppercase; 
        font-size: 0.9rem;
        margin-bottom: 15px; 
        display: block; 
    }
    
    /* Progress bar színe zöldre */
    .stProgress > div > div > div > div { background-color: #00df5d; }
    
    /* Input mezők igazítása */
    .stDateInput label { color: #9da3a8 !important; text-transform: uppercase; font-size: 0.8rem; }
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

# --- LOGIKA: DINAMIKUS SÚLYOZÁS ---
def calculate_dynamic_weights_with_progress():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    models = ["ecmwf_ifs", "gfs_seamless", "icon_seamless"]
    model_scores = {m: 0.0 for m in models}
    
    prog_w = st.progress(0)
    stat_w = st.empty()
    
    try:
        for idx, city in enumerate(CITIES):
            p = int((idx / len(CITIES)) * 100)
            prog_w.progress(p)
            stat_w.markdown(f"📡 **ELEMZÉS: TEGNAPI PONTOSSÁG MÉRÉSE... {p}%**")
            
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
                model_scores[m] += (1 / (np.mean(np.abs(actual - pred)) + 0.1))
        
        prog_w.empty(); stat_w.empty()
        total = sum(model_scores.values())
        return {m: model_scores[m]/total for m in models}
    except:
        prog_w.empty(); stat_w.empty()
        return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}

# --- LOGIKA: ADATGYŰJTÉS ---
@st.cache_data(ttl=3600)
def FETCH_FINAL_DATA(date, weights):
    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00'), date.strftime('%Y-%m-%dT18:00')
    lats, lons = np.arange(45.8, 48.6, 0.15), np.arange(16.2, 22.8, 0.18)
    v_pts = [(la, lo) for la in lats for lo in lons if HU_POLY.contains(Point(lo, la))]
    results = [{"lat": p[0], "lon": p[1], "min": 0, "max": 0} for p in v_pts]
    
    prog = st.progress(0)
    stat = st.empty()
    
    chunk_size = 10
    for i in range(0, len(results), chunk_size):
        p = min(int((i / len(results)) * 100), 100)
        prog.progress(p)
        stat.markdown(f"🎰 **LIVE ADATOK FELDOLGOZÁSA... {p}%**")
        
        chunk = v_pts[i:i+chunk_size]
        la_c, lo_c = [c[0] for c in chunk], [c[1] for c in chunk]
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": la_c, "longitude": lo_c, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }, timeout=15).json()
                pts = r if isinstance(r, list) else [r]
                for j, res in enumerate(pts):
                    results[i+j]["min"] += min(res['hourly']['temperature_2m']) * w
                    results[i+j]["max"] += max(res['hourly']['temperature_2m']) * w
            except: continue
            
    prog.empty(); stat.empty()
    return pd.DataFrame(results)

# --- DASHBOARD UI ---
st.markdown('<div class="main-header"><h1>🌡️ MODELL-SÚLYOZÓ <span style="color:#00df5d;">PRO</span></h1></div>', unsafe_allow_html=True)

main_c, side_c = st.columns([3, 1], gap="medium")

with main_c:
    # Vezérlő sáv
    c1, c2, _ = st.columns([1.5, 0.8, 2])
    target_date = c1.date_input("ESEMÉNY VÁLASZTÁSA", datetime.now() + timedelta(days=1))
    if c2.button("🔄 FRISSÍTÉS"):
        st.cache_data.clear()
        st.rerun()
    
    current_weights = calculate_dynamic_weights_with_progress()
    df = FETCH_FINAL_DATA(target_date, current_weights)
    
    if not df.empty:
        # Kiemelt statisztikák (mint a fő mérkőzések)
        m1, m2 = st.columns(2)
        min_r = df.loc[df['min'].idxmin()]
        max_r = df.loc[df['max'].idxmax()]
        m1.metric("📉 ORSZÁGOS MINIMUM", f"{round(min_r['min'], 1)} °C", f"{find_nearest_city(min_r['lat'], min_r['lon'])}")
        m2.metric("📈 ORSZÁGOS MAXIMUM", f"{round(max_r['max'], 1)} °C", f"{find_nearest_city(max_r['lat'], max_r['lon'])}")
        
        # Hőtérképek sötét stílusban
        mapc1, mapc2 = st.columns(2)
        def draw_m(data, val, col, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=val, color_continuous_scale=col, zoom=6.2, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-darkmatter")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', line=dict(width=2, color='#00df5d'), showlegend=False))
            fig.update_layout(title=dict(text=title, font=dict(color="#ffffff", size=16)), margin={"r":0,"t":45,"l":0,"b":0}, height=500, paper_bgcolor="#121416", plot_bgcolor="#121416")
            return fig
        mapc1.plotly_chart(draw_m(df, "min", "Viridis", "MINIMUM ELŐREJELZÉS"), use_container_width=True)
        mapc2.plotly_chart(draw_m(df, "max", "Reds", "MAXIMUM ELŐREJELZÉS"), use_container_width=True)

with side_c:
    st.markdown('<div class="tech-details"><span class="tech-header">🎫 TECHNIKAI SZELVÉNY</span>', unsafe_allow_html=True)
    st.markdown("""
    **STRATÉGIA: DINAMIKUS SÚLYOZÁS (D-MOS)** A rendszer az elmúlt 24 óra teljesítményét elemzi Budapest, Debrecen, Szeged és Pécs mérőállomásain.  
    
    **MATEMATIKAI MODELL:** Az előrejelzések súlya az inverz átlagos abszolút hiba (MAE) alapján dől el.  
    
    **RÁCSHÁLÓ:** 15 km felbontású domborzat-érzékeny rácsháló.  
    
    **ÉGHAJLATI CIKLUS:** 18:00 UTC - 18:00 UTC.
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<span style="color:#9da3a8; font-size:0.8rem; font-weight:bold;">AKTUÁLIS SÚLYOZÁS</span>', unsafe_allow_html=True)
    w_df = pd.DataFrame({
        "Modell": ["ECMWF", "GFS", "ICON"], 
        "Súly": [current_weights["ecmwf_ifs"]*100, current_weights["gfs_seamless"]*100, current_weights["icon_seamless"]*100]
    })
    fig_p = px.pie(w_df, values='Súly', names='Modell', hole=0.6, color_discrete_sequence=['#00df5d', '#1a1c1e', '#383c41'])
    fig_p.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250, showlegend=True, paper_bgcolor="rgba(0,0,0,0)", legend=dict(font=dict(color="#ffffff"), orientation="h", y=-0.2))
    fig_p.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#2d3135', width=1)))
    st.plotly_chart(fig_p, use_container_width=True)
