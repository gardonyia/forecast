import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. UI KONFIGURÁCIÓ (V8 STÍLUS) ---
st.set_page_config(page_title="Met-Ensemble v27.0", layout="wide")

st.markdown("""
    <style>
    .main .block-container { max-width: 1000px; padding-top: 1.5rem; }
    .result-card {
        background-color: #ffffff; padding: 30px; border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1); text-align: center;
        border: 1px solid #e2e8f0; margin-bottom: 20px;
    }
    .temp-val { font-size: 5rem; font-weight: 900; margin: 5px 0; letter-spacing: -3px; line-height: 1; }
    .label { font-size: 1rem; color: #64748b; font-weight: 700; text-transform: uppercase; margin-bottom: 10px; }
    .city-info { font-size: 1.3rem; color: #1e293b; font-weight: 600; margin-top: 10px; }
    .time-stamp { font-family: monospace; font-size: 0.85rem; color: #94a3b8; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ROBUST 18-18 UTC ENGINE ---
def run_final_scan(target_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # Időablak definiálása UTC-ben
    # T-1 nap 18:00-tól T nap 18:00-ig
    start_time = datetime.combine(target_date - timedelta(days=1), datetime.min.time()).replace(hour=18)
    end_time = datetime.combine(target_date, datetime.min.time()).replace(hour=18)
    
    # Kezdőértékek javítása (None helyett extrém távoli érték)
    g_min = {"val": float('inf'), "city": "N/A", "time": "N/A"}
    g_max = {"val": float('-inf'), "city": "N/A", "time": "N/A"}

    # Batch feldolgozás (500 településenként az API limit miatt)
    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # Lekérjük az összes fáklyaszálat (ensemble=true)
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={start_time.strftime('%Y-%m-%d')}&end_date={end_time.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            if not isinstance(res, list): res = [res]
            
            for idx, r in enumerate(res):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                
                # Végigpásztázzuk az összes tagot (member00-50)
                for member_key, temps in hourly.items():
                    if 'temperature_2m' in member_key:
                        for t_idx, temp in enumerate(temps):
                            if temp is None: continue
                            
                            curr_t = datetime.fromisoformat(times[t_idx])
                            # Csak a kért 18-18 UTC ablakban vizsgálunk
                            if start_time <= curr_t <= end_time:
                                if temp < g_min["val"]:
                                    g_min = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
                                if temp > g_max["val"]:
                                    g_max = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
        except: continue

    return g_min, g_max

# --- 3. DASHBOARD ---
st.title("ECMWF 18-18 UTC Scanner v27.0")

# Alapértelmezett dátum a kritikus január 9-re állítva
selected_date = st.date_input("Céldátum:", value=datetime(2026, 1, 9))

st.write("---")

if st.button("ORDSZÁGOS SZKENNELÉS INDÍTÁSA"):
    with st.spinner("3155 település 51 fáklyaszálának elemzése..."):
        n_min, n_max = run_final_scan(selected_date)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"""
            <div class="result-card">
                <div class="label">Országos Minimum (Fáklya Legalja)</div>
                <div class="temp-val" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
                <div class="city-info">📍 {n_min['city']}</div>
                <div class="time-stamp">Időpont: {n_min['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
            <div class="result-card">
                <div class="label">Országos Maximum (Fáklya Teteje)</div>
                <div class="temp-val" style="color:#dc2626;">{round(n_max['val'], 1)} °C</div>
                <div class="city-info">📍 {n_max['city']}</div>
                <div class="time-stamp">Időpont: {n_max['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    st.caption(f"Vizsgált periódus: {selected_date - timedelta(days=1)} 18:00 UTC – {selected_date} 18:00 UTC.")
