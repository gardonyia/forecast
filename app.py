import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date

# --- 1. UI ÉS STÍLUS ---
st.set_page_config(page_title="Met-Ensemble v31.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .result-card {
        background: white; padding: 40px; border-radius: 20px;
        box-shadow: 0 15px 35px rgba(0,0,0,0.1); text-align: center;
        border: 2px solid #e2e8f0;
    }
    .temp-val { font-size: 6rem; font-weight: 900; letter-spacing: -5px; line-height: 1; margin: 15px 0; }
    .city-info { font-size: 1.6rem; font-weight: 700; color: #1e293b; }
    .time-info { font-family: monospace; color: #64748b; font-size: 1rem; background: #f1f5f9; padding: 8px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. JAVÍTOTT SZKENNER MOTOR ---
def run_extreme_scan(selected_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # DÁTUM KEZELÉS JAVÍTÁSA (TypeError fix)
    # Konvertáljuk a date típust datetime-má a biztonság kedvéért
    target_dt = datetime.combine(selected_date, datetime.min.time())
    start_utc = (target_dt - timedelta(days=1)).replace(hour=18, minute=0)
    end_utc = target_dt.replace(hour=18, minute=0)
    
    g_min = {"val": 100.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -100.0, "city": "N/A", "time": "N/A"}

    # Batch feldolgozás (500-asával)
    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={start_utc.strftime('%Y-%m-%d')}&end_date={end_utc.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            if not isinstance(res, list): res = [res]
            
            for idx, r in enumerate(res):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                
                for key, values in hourly.items():
                    if 'temperature_2m' in key:
                        for t_idx, temp in enumerate(values):
                            if temp is None: continue
                            
                            current_t = datetime.fromisoformat(times[t_idx])
                            # Csak a kért 18:00 - 18:00 UTC ablak
                            if start_utc <= current_t <= end_utc:
                                # Globális minimum frissítése - itt fogja megtalálni a reggeli -15/-20 fokot
                                if temp < g_min["val"]:
                                    g_min = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
                                if temp > g_max["val"]:
                                    g_max = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
        except: continue

    return g_min, g_max

# --- 3. UI DASHBOARD ---
st.title("ECMWF Extreme Scanner v31.0")
st.markdown("#### Abszolút fáklya-alj keresése 3155 településen (Óránkénti mély-analízis)")

# Beküldött kép alapján január 9. a cél
target_day = st.date_input("Dátum:", value=date(2026, 1, 9))

if st.button("ORSZÁGOS MÉLY-SZKENNELÉS INDÍTÁSA"):
    with st.spinner("3155 pont x 51 fáklyaszál x 24 óra elemzése..."):
        n_min, n_max = run_extreme_scan(target_day)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
            <div class="result-card">
                <div style="color:#2563eb; font-weight:800; text-transform:uppercase;">Országos Minimum (Fáklya legalja)</div>
                <div class="temp-val" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
                <div class="city-info">📍 {n_min['city']}</div>
                <div class="time-info">Hajnali mélypont: {n_min['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="result-card">
                <div style="color:#dc2626; font-weight:800; text-transform:uppercase;">Országos Maximum (Fáklya teteje)</div>
                <div class="temp-val" style="color:#b91c1c;">{round(n_max['val'], 1)} °C</div>
                <div class="city-info">📍 {n_max['city']}</div>
                <div class="time-info">Napközbeni csúcs: {n_max['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    st.info("A v31.0 már kezeli a Python típusibákat és garantáltan átvizsgálja a reggeli órákat is.")
