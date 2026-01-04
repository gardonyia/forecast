import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 1. UX/UI KONFIGURÁCIÓ (V8 ALAPJÁN) ---
st.set_page_config(page_title="Met-Ensemble v20.0", layout="wide")

st.markdown("""
    <style>
    .main .block-container { max-width: 1000px; padding-top: 2rem; }
    .result-card {
        background-color: #ffffff; padding: 30px; border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); text-align: center;
        border: 1px solid #f1f5f9;
    }
    .temp-display { font-size: 3.8rem; font-weight: 900; margin: 10px 0; letter-spacing: -1px; }
    .loc-text { font-size: 1.1rem; color: #64748b; font-weight: 600; }
    .tech-log { 
        background: #0f172a; color: #94a3b8; padding: 20px; 
        border-radius: 8px; font-family: 'Courier New', monospace; font-size: 0.8rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SZEZONÁLIS ÉS TECHNIKAI LOGIKA ---
def get_system_params(target_date):
    month = target_date.month
    # Okos szezon-kapcsoló beépítve a mentett utasítás alapján
    is_winter = month in [11, 12, 1, 2, 3]
    return {
        "is_winter": is_winter,
        "mode": "TÉLI (Extrém Fáklya-Alj)" if is_winter else "NYÁRI (Fáklya-Tető)",
        "zabar_factor": -2.5, # Fix korrekció
        "threshold": -13
    }

# --- 3. ECMWF ABSZOLÚT FÁKLYA MOTOR ---
def run_absolute_plume_analysis(target_date, cfg):
    try:
        # Teljes magyar településadatbázis
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Zabar", "lat": 48.15, "lng": 20.25}, {"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # Időintervallum meghatározása
    t_start = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_end = target_date.strftime('%Y-%m-%d')
    
    final_data = []
    
    # Kötegelt feldolgozás (800 település / API hívás)
    for i in range(0, len(towns), 800):
        batch = towns[i:i+800]
        lats = [t['lat'] for t in batch]
        lons = [t['lng'] for t in batch]
        
        # Kizárólag az ECMWF valószínűségi (ensemble) adatok lekérése
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={t_start}&end_date={t_end}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                all_member_mins = []
                all_member_maxs = []
                
                # Végigmegyünk az összes ensemble tagon (member00...member50)
                for key, values in hourly.items():
                    if 'temperature_2m' in key and values:
                        valid_temps = [v for v in values if v is not None]
                        if valid_temps:
                            all_member_mins.append(min(valid_temps))
                            all_member_maxs.append(max(valid_temps))
                
                if all_member_mins:
                    # AZ ALJA A MINIMUM, A TETEJE A MAXIMUM
                    abs_min = min(all_member_mins)
                    abs_max = max(all_member_maxs)
                    
                    # Zabar-faktor és téli korrekció alkalmazása
                    if cfg["is_winter"] and abs_min < cfg["threshold"]:
                        abs_min += cfg["zabar_factor"]
                        
                    final_data.append({
                        "n": batch[idx]['name'],
                        "min": abs_min,
                        "max": abs_max
                    })
        except: pass

    return pd.DataFrame(final_data)

# --- 4. INTERAKTÍV DASHBOARD ---
st.title("Met-Ensemble Pro v20.0")

# Alapállás: Futtatás + 1 nap
default_date = datetime.now() + timedelta(days=1)
selected_date = st.date_input("Válasszon dátumot:", value=default_date)
config = get_system_params(selected_date)

st.write("---")

with st.spinner(f"ECMWF Fáklya-szélsőértékek elemzése 3155 településre..."):
    df_results = run_absolute_plume_analysis(selected_date, config)
    res_min = df_results.loc[df_results['min'].idxmin()]
    res_max = df_results.loc[df_results['max'].idxmax()]

# Megjelenítés kártyákon
col_left, col_right = st.columns(2)

with col_left:
    st.markdown(f"""
        <div class="result-card">
            <div style="text-transform:uppercase; font-size:0.8rem; font-weight:700; color:#1e40af;">Országos Minimum (Fáklya alja)</div>
            <div class="temp-display" style="color:#1e40af;">{round(res_min['min'], 1)} °C</div>
            <div class="loc-text">📍 {res_min['n']}</div>
        </div>
    """, unsafe_allow_html=True)

with col_right:
    st.markdown(f"""
        <div class="result-card">
            <div style="text-transform:uppercase; font-size:0.8rem; font-weight:700; color:#dc2626;">Országos Maximum (Fáklya teteje)</div>
            <div class="temp-display" style="color:#dc2626;">{round(res_max['max'], 1)} °C</div>
            <div class="loc-text">📍 {res_max['n']}</div>
        </div>
    """, unsafe_allow_html=True)

# --- 5. TECHNIKAI DOKUMENTÁCIÓ ---
st.write("<br>", unsafe_allow_html=True)
st.markdown(f"""
    <div class="tech-log">
        <b>[VERSION]:</b> 20.0 Absolute Plume Edition<br>
        <b>[OKOS SZEZON-KAPCSOLÓ]:</b> {config['mode']} aktív.<br>
        <b>[METHOD]:</b> Kizárólagos ECMWF ENS szélsőérték-keresés (No-Average Logic).<br>
        <b>[ZABAR_FACTOR]:</b> {config['zabar_factor']} °C alkalmazva {config['threshold']} °C alatt.<br>
        <b>[DATE_CONTEXT]:</b> {selected_date.strftime('%Y-%m-%d')} elemzése az összes magyar település rácspontján.
    </div>
""", unsafe_allow_html=True)
