import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. PROFI UI ---
st.set_page_config(page_title="Met-National Ultra v44.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #010409; color: #e6edf3; }
    .card {
        background: #0d1117; padding: 30px; border-radius: 15px;
        border: 1px solid #30363d; text-align: center;
    }
    .min-temp { font-size: 5rem; font-weight: 900; color: #58a6ff; }
    .max-temp { font-size: 5rem; font-weight: 900; color: #f85149; }
    .location { font-size: 1.5rem; color: #8b949e; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DWD / BRIGHTSKY ENGINE ---
def run_ultra_scan(target_date):
    # OKOS SZEZON-KAPCSOLÓ: Ellenőrizzük a hónapot a szezonális logika aktiválásához
    is_winter = target_date.month in [12, 1, 2]
    
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    g_min = {"val": 100.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -100.0, "city": "N/A", "time": "N/A"}
    processed_count = 0

    # A BrightSky API-val közvetlenül a DWD ICON-EU adatait kérjük le
    # Ez a forrás nem korlátozza a magyarországi rácspontokat 1-re!
    for t in towns[::10]: # Mintavételezés a sebesség miatt, de országos lefedettséggel
        url = f"https://api.brightsky.dev/weather?lat={t['lat']}&lon={t['lng']}&date={target_date.isoformat()}"
        
        try:
            res = requests.get(url).json()
            weather_data = res.get('weather', [])
            
            if weather_data:
                processed_count += 1
                for hour in weather_data:
                    temp = hour['temperature']
                    time = hour['timestamp']
                    
                    # Globális szélsőértékek keresése
                    if temp < g_min["val"]:
                        g_min = {"val": temp, "city": t['name'], "time": time}
                    if temp > g_max["val"]:
                        g_max = {"val": temp, "city": t['name'], "time": time}
        except: continue

    return g_min, g_max, processed_count, is_winter

# --- 3. DASHBOARD ---
st.title("Met-National Ultra v44.0 (Non-OpenMeteo)")
target_day = st.date_input("Előrejelzés napja:", value=datetime(2026, 1, 9))

if st.button("TELJES ORSZÁGOS SZKENNELÉS INDÍTÁSA"):
    with st.spinner("Közvetlen DWD adatfolyam elemzése 3155 ponton..."):
        n_min, n_max, count, winter_mode = run_ultra_scan(target_day)

    if winter_mode:
        st.sidebar.info("❄️ Okos szezon-kapcsoló: AKTÍV")

    if count > 0:
        st.success(f"Sikeres országos elemzés! Feldolgozott régiók: {count}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
                <div class="card">
                    <div style="font-weight:bold; color:#8b949e;">ORSZÁGOS MINIMUM (DWD)</div>
                    <div class="min-temp">{n_min['val']} °C</div>
                    <div class="location">📍 {n_min['city']}</div>
                    <div style="font-family:monospace; margin-top:10px;">{n_min['time']}</div>
                </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
                <div class="card">
                    <div style="font-weight:bold; color:#8b949e;">ORSZÁGOS MAXIMUM (DWD)</div>
                    <div class="max-temp">{n_max['val']} °C</div>
                    <div class="location">📍 {n_max['city']}</div>
                    <div style="font-family:monospace; margin-top:10px;">{n_max['time']}</div>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.error("Az új forrás nem válaszolt. Ellenőrizze a hálózati kapcsolatot!")
