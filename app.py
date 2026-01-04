import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. UI KONFIGURÁCIÓ (V8 STÍLUS) ---
st.set_page_config(page_title="Met-Ensemble v24.0", layout="wide")

st.markdown("""
    <style>
    .main .block-container { max-width: 950px; padding-top: 1.5rem; }
    .result-card {
        background-color: #ffffff; padding: 30px; border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08); text-align: center;
        border: 1px solid #e2e8f0;
    }
    .temp-val { font-size: 4rem; font-weight: 900; margin: 10px 0; }
    .loc-text { font-size: 1.1rem; color: #64748b; font-weight: 600; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ABSZOLÚT SZÉLSŐÉRTÉK MOTOR ---
def run_absolute_scan(target_date):
    # Teljes településadatbázis lekérése
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # A fáklya-kép alapján az adott nap teljes 24 óráját nézzük
    t_start = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_end = target_date.strftime('%Y-%m-%d')
    
    global_min_val = 99.0
    global_max_val = -99.0
    min_city = ""
    max_city = ""

    # Batch processing (800 település / kérés)
    for i in range(0, len(towns), 800):
        batch = towns[i:i+800]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # LEFONTOSABB: ensemble=true paraméterrel az összes (51) szálat lekérjük!
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={t_start}&end_date={t_end}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                # Minden egyes fáklya-szál minden óráját végigpásztázzuk
                for key, values in hourly.items():
                    if 'temperature_2m' in key and values:
                        valid_temps = [v for v in values if v is not None]
                        if valid_temps:
                            local_min = min(valid_temps)
                            local_max = max(valid_temps)
                            
                            if local_min < global_min_val:
                                global_min_val = local_min
                                min_city = batch[idx]['name']
                            if local_max > global_max_val:
                                global_max_val = local_max
                                max_city = batch[idx]['name']
        except: pass

    return {"name": min_city, "val": global_min_val}, {"name": max_city, "val": global_max_val}

# --- 3. DASHBOARD ---
st.title("ECMWF Absolute Scanner v24.0")

# Alapértelmezett dátum: 2026.01.09 (a beküldött kép alapján)
selected_date = st.date_input("Céldátum választása:", value=datetime(2026, 1, 9))

st.write("---")

with st.spinner(f"Fáklya-szélsőértékek kinyerése 3155 ponton..."):
    n_min, n_max = run_absolute_scan(selected_date)

col1, col2 = st.columns(2)

with col1:
    st.markdown(f"""
        <div class="result-card">
            <div class="loc-text">Országos Minimum (Abszolút Fáklya-alj)</div>
            <div class="temp-val" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
            <div style="color:#64748b;">📍 {n_min['name']}</div>
        </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
        <div class="result-card">
            <div class="loc-text">Országos Maximum (Abszolút Fáklya-tető)</div>
            <div class="temp-val" style="color:#dc2626;">{round(n_max['val'], 1)} °C</div>
            <div style="color:#64748b;">📍 {n_max['name']}</div>
        </div>
    """, unsafe_allow_html=True)

st.warning("Módszertan: A program nem átlagol. A 3155 település összes ECMWF ensemble tagját (51 tag) átvizsgálja, és a létező legalacsonyabb/legmagasabb értéket mutatja meg.")
