import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 1. PRO UI/UX (SÖTÉT MÓD, ADATKÖZPONTÚ) ---
st.set_page_config(page_title="Met-Ensemble Pro v18.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .main .block-container { max-width: 1100px; padding-top: 1rem; }
    
    /* Adat kártyák */
    .data-card {
        background: #1e293b;
        padding: 24px;
        border-radius: 8px;
        border: 1px solid #334155;
        text-align: left;
    }
    .main-temp { font-size: 4rem; font-weight: 900; line-height: 1; letter-spacing: -2px; margin: 10px 0; }
    .status-badge {
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: 800;
        text-transform: uppercase;
        background: #334155;
        color: #94a3b8;
    }
    
    /* Technikai blokk */
    .tech-box {
        background: #0f172a;
        border-left: 4px solid #3b82f6;
        padding: 15px;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        color: #94a3b8;
        line-height: 1.5;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. OKOS SZEZON-KAPCSOLÓ ÉS TECHNIKAI LOGIKA ---
def get_system_config(date):
    month = date.month
    # Okos szezon-kapcsoló: Nov-Márc téli logika
    is_winter = month in [11, 12, 1, 2, 3]
    return {
        "season_mode": "WINTER_VALLEY_LOGIC" if is_winter else "SUMMER_UHI_LOGIC",
        "is_winter": is_winter,
        "zabar_factor": -2.5,  # Fix korrekció
        "threshold": -13,
        "bias_strength": 0.95  # 95%-os eltolás az extrém felé
    }

# --- 3. EXTRÉM ANALÍZIS ENGINE ---
def run_extreme_engine(date, cfg):
    models = {"ecmwf_ifs": 0.40, "icon_eu": 0.45, "gfs_seamless": 0.15}
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Zabar", "lat": 48.15, "lng": 20.25}, {"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')
    results = []

    for i in range(0, len(towns), 800):
        batch = towns[i:i+800]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        df = pd.DataFrame([{"n": t['name'], "min": 0.0, "max": 0.0, "raw_mins": []} for t in batch])

        for m_id, w in models.items():
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_s}&end_date={t_e}&timezone=UTC"
                res = requests.get(url).json()
                res_list = res if isinstance(res, list) else [res]
                
                for idx, r in enumerate(res_list):
                    t_data = [t for t in r.get('hourly', {}).get('temperature_2m', []) if t is not None]
                    if t_data:
                        m_min = min(t_data)
                        df.at[idx, "min"] += m_min * w
                        df.at[idx, "max"] += max(t_data) * w
                        df.at[idx, "raw_mins"].append(m_min)
            except: pass

        # --- A KRITIKUS SZÁMÍTÁSI KORREKCIÓ ---
        for idx in range(len(df)):
            if df.at[idx, "raw_mins"]:
                abs_min = min(df.at[idx, "raw_mins"])
                if cfg["is_winter"]:
                    # Ha extrém lehűlés jelei mutatkoznak, eldobjuk az átlagot
                    if abs_min < -5:
                        # Völgy-dinamika: 95% súly a leghidegebb modellnek
                        df.at[idx, "min"] = (df.at[idx, "min"] * 0.05) + (abs_min * 0.95)
                    
                    # Zabar-faktor: Fix degresszió szélsőséges esetben
                    if abs_min < cfg["threshold"]:
                        df.at[idx, "min"] += cfg["zabar_factor"]
                else:
                    if df.at[idx, "min"] > 18: df.at[idx, "min"] += 2.2 # UHI
        results.append(df)
    
    return pd.concat(results)

# --- 4. UI MEGJELENÍTÉS ---
st.title("MET-ENSEMBLE PRO // V18.0")
target_date = st.date_input("SELECT TARGET DATE:", value=datetime(2026, 1, 9))
cfg = get_system_config(target_date)

st.write("---")

with st.spinner("CALCULATING VALLEY DYNAMICS..."):
    data = run_extreme_engine(target_date, cfg)
    res_min = data.loc[data['min'].idxmin()]
    res_max = data.loc[data['max'].idxmax()]

c1, c2 = st.columns(2)

with c1:
    st.markdown(f"""
    <div class="data-card">
        <span class="status-badge" style="color:#60a5fa">National Minimum</span>
        <div class="main-temp" style="color:#60a5fa">{round(res_min['min'], 1)}°C</div>
        <div style="color:#94a3b8; font-weight:600;">📍 {res_min['n']}</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="data-card">
        <span class="status-badge" style="color:#f87171">National Maximum</span>
        <div class="main-temp" style="color:#f87171">{round(res_max['max'], 1)}°C</div>
        <div style="color:#94a3b8; font-weight:600;">📍 {res_max['n']}</div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. RÉSZLETES TECHNIKAI DOKUMENTÁCIÓ ---
st.write("<br>", unsafe_allow_html=True)
st.subheader("TECHNICAL LOG & SYSTEM DOCUMENTATION")

t_col1, t_col2 = st.columns(2)

with t_col1:
    st.markdown(f"""
    <div class="tech-box">
        <b>[SYSTEM_SWITCH]: {cfg['season_mode']}</b><br>
        A rendszer dátum-alapú triggereket használ. Nov 01 - Marc 31 között a Fagyzug-logika aktív.
        <br><br>
        <b>[CALCULATION_MODEL]: ABSOLUTE_MIN_BIAS</b><br>
        Az átlagolás (Mean) hibáját kiküszöbölendő, -5°C alatt a rendszer 95%-os súlyozással a leghidegebb rácspont-értéket (ICON-EU/ECMWF) emeli ki. Ez biztosítja, hogy a völgyekben kialakuló mikroklimatikus extrém hideg ne tűnjön el az átlagban.
    </div>
    """, unsafe_allow_html=True)

with t_col2:
    st.markdown(f"""
    <div class="tech-box">
        <b>[ZABAR_FACTOR]: {cfg['zabar_factor']}°C</b><br>
        Alkalmazva: Ha T(min) < {cfg['threshold']}°C.<br>
        Cél: A topográfiai felbontásból adódó (9km vs valóság) szisztematikus hiba korrekciója.
        <br><br>
        <b>[ENSEMBLE_WEIGHTS]:</b><br>
        - ICON-EU: 45% (High Res)<br>
        - ECMWF: 40% (Global Stability)<br>
        - GFS: 15% (Correction)
    </div>
    """, unsafe_allow_html=True)
