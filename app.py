import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. MINIMALISTA UI (v8 ALAPJÁN) ---
st.set_page_config(page_title="Met-Ensemble v23.0", layout="wide")

st.markdown("""
    <style>
    .main .block-container { max-width: 900px; padding-top: 1.5rem; }
    .result-card {
        background-color: #ffffff; padding: 25px; border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center;
        border: 1px solid #e2e8f0; margin-bottom: 20px;
    }
    .temp-val { font-size: 3.5rem; font-weight: 800; margin: 5px 0; letter-spacing: -2px; }
    .label { font-size: 0.9rem; color: #64748b; font-weight: 600; text-transform: uppercase; }
    .city { font-size: 1.1rem; color: #1e293b; font-weight: 500; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. PURE ECMWF ENGINE ---
def run_pure_plume_scan(target_date):
    # 3155 magyar település koordinátái
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}, {"name": "Zabar", "lat": 48.15, "lng": 20.25}]

    # Időintervallum (a fáklya alapján az adott nap 24 órája)
    t_start = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_end = target_date.strftime('%Y-%m-%d')
    
    all_node_extremes = []

    # Batch hívások (800 település egyszerre)
    for i in range(0, len(towns), 800):
        batch = towns[i:i+800]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # Kizárólag ECMWF Ensemble (minden tag: member00-50)
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={t_start}&end_date={t_end}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                member_values = []
                
                # Begyűjtjük az összes fáklya-szál (tag) értékét az adott napra
                for key, values in hourly.items():
                    if 'temperature_2m' in key and values:
                        member_values.extend([v for v in values if v is not None])
                
                if member_values:
                    all_node_extremes.append({
                        "name": batch[idx]['name'],
                        "min": min(member_values),
                        "max": max(member_values)
                    })
        except: pass

    # Országos szélsőértékek keresése (A 3155 minimum legkisebbje és a 3155 maximum legnagyobbja)
    national_min = min(all_node_extremes, key=lambda x: x['min'])
    national_max = max(all_node_extremes, key=lambda x: x['max'])
    
    return national_min, national_max

# --- 3. UI MEGJELENÍTÉS ---
st.title("ECMWF Ensemble Scanner v23.0")

# Alapállás: Ma + 1 nap (Dátumválasztó)
selected_date = st.date_input("Céldátum választása:", value=datetime.now() + timedelta(days=1))

st.write("---")

with st.spinner(f"Szélsőértékek kinyerése 3155 ECMWF fáklyából..."):
    n_min, n_max = run_pure_plume_scan(selected_date)

col1, col2 = st.columns(2)

with col1:
    st.markdown(f"""
        <div class="result-card">
            <div class="label">Országos Minimum (Fáklya alja)</div>
            <div class="temp-val" style="color:#2563eb;">{round(n_min['min'], 1)} °C</div>
            <div class="city">📍 {n_min['name']}</div>
        </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
        <div class="result-card">
            <div class="label">Országos Maximum (Fáklya teteje)</div>
            <div class="temp-val" style="color:#dc2626;">{round(n_max['max'], 1)} °C</div>
            <div class="city">📍 {n_max['name']}</div>
        </div>
    """, unsafe_allow_html=True)

st.info(f"Módszertan: A program 3155 magyarországi ponton végzi el az ECMWF 51 tagú valószínűségi előrejelzésének (ENS) elemzését. Eredményként a teljes adathalmaz abszolút minimumát és maximumát jelenítjük meg.")
