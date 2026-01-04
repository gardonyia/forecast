import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. UI KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-Ensemble v26.0", layout="wide")

st.markdown("""
    <style>
    .main .block-container { max-width: 900px; padding-top: 1.5rem; }
    .result-card {
        background-color: #ffffff; padding: 30px; border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08); text-align: center;
        border: 1px solid #e2e8f0; margin-bottom: 20px;
    }
    .temp-val { font-size: 4.5rem; font-weight: 900; margin: 5px 0; letter-spacing: -3px; }
    .label { font-size: 0.9rem; color: #64748b; font-weight: 700; text-transform: uppercase; }
    .city { font-size: 1.2rem; color: #1e293b; font-weight: 600; }
    .tech-info { font-family: monospace; font-size: 0.8rem; color: #94a3b8; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 18-18 UTC SCAN ENGINE ---
def run_18_18_scan(target_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}, {"name": "Zabar", "lat": 48.15, "lng": 20.25}]

    # Időablak beállítása: T-1 nap 18:00 UTC-től T nap 18:00 UTC-ig
    start_dt = target_date - timedelta(days=1)
    end_dt = target_date
    
    g_min = {"val": 99.0, "city": "", "time": ""}
    g_max = {"val": -99.0, "city": "", "time": ""}

    # Batch hívások
    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # Lekérjük a szükséges napokat (T-1 és T)
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={start_dt.strftime('%Y-%m-%d')}&end_date={end_dt.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                
                # Meghatározzuk az indexeket a 18:00 - 18:00 ablakhoz
                # (Az Open-Meteo órás bontásban adja vissza az adatokat)
                for member_key, values in hourly.items():
                    if 'temperature_2m' in member_key:
                        for t_idx, val in enumerate(values):
                            if val is None: continue
                            
                            # Csak a kért 18:00 - 18:00 UTC közötti órákat vizsgáljuk
                            current_time = datetime.fromisoformat(times[t_idx])
                            check_start = start_dt.replace(hour=18, minute=0)
                            check_end = end_dt.replace(hour=18, minute=0)
                            
                            if check_start <= current_time <= check_end:
                                if val < g_min["val"]:
                                    g_min["val"] = val
                                    g_min["city"] = batch[idx]['name']
                                    g_min["time"] = times[t_idx]
                                if val > g_max["val"]:
                                    g_max["val"] = val
                                    g_max["city"] = batch[idx]['name']
                                    g_max["time"] = times[t_idx]
        except: pass

    return g_min, g_max

# --- 3. UI ---
st.title("ECMWF 18-18 UTC Absolute Scanner v26.0")

# Alapértelmezett dátum: 2026.01.09
selected_date = st.date_input("Céldátum:", value=datetime(2026, 1, 9))

st.write("---")

with st.spinner(f"Fáklya-szélsőértékek kinyerése 3155 ponton (18:00 UTC - 18:00 UTC)..."):
    n_min, n_max = run_18_18_scan(selected_date)

c1, c2 = st.columns(2)

with c1:
    st.markdown(f"""
        <div class="result-card">
            <div class="label">Országos Minimum (Fáklya legalja)</div>
            <div class="temp-val" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
            <div class="city">📍 {n_min['city']}</div>
            <div class="tech-info">Időpont: {n_min['time']} UTC</div>
        </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
        <div class="result-card">
            <div class="label">Országos Maximum (Fáklya teteje)</div>
            <div class="temp-val" style="color:#dc2626;">{round(n_max['val'], 1)} °C</div>
            <div class="city">📍 {n_max['city']}</div>
            <div class="tech-info">Időpont: {n_max['time']} UTC</div>
        </div>
    """, unsafe_allow_html=True)

st.caption(f"Vizsgált időszak: {(selected_date - timedelta(days=1)).strftime('%Y-%m-%d')} 18:00 UTC – {selected_date.strftime('%Y-%m-%d')} 18:00 UTC.")
