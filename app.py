import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. UI KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-ICON v40.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .result-card {
        background: white; padding: 40px; border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1); text-align: center;
        border-top: 8px solid #0369a1;
    }
    .temp-val { font-size: 6rem; font-weight: 950; color: #0369a1; line-height: 1; }
    .city-label { font-size: 1.8rem; font-weight: 700; color: #334155; margin-top: 10px; }
    .source-tag { background: #e0f2fe; color: #0369a1; padding: 5px 15px; border-radius: 10px; font-size: 0.9rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ALTERNATÍV DWD ADATFORRÁS ---
def run_direct_dwd_scan(target_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    target_dt = datetime.combine(target_date, datetime.min.time())
    start_utc = (target_dt - timedelta(days=1)).replace(hour=18)
    end_utc = target_dt.replace(hour=18)
    
    g_min = {"val": 100.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -100.0, "city": "N/A", "time": "N/A"}
    success_count = 0

    # Kisebb csomagokban kérjük le a stabilabb válaszért (Direct DWD Access)
    for i in range(0, len(towns), 300):
        batch = towns[i:i+300]
        lats = [str(t['lat']) for t in batch]
        lons = [str(t['lng']) for t in batch]
        
        # Ez a végpont közvetlenebbül éri el a DWD ICON-EU rácspontjait
        url = (f"https://api.open-meteo.com/v1/dwd-icon?latitude={','.join(lats)}&longitude={','.join(lons)}"
               f"&hourly=temperature_2m&icon_model=icon_eu"
               f"&start_date={start_utc.strftime('%Y-%m-%d')}&end_date={end_utc.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                temps = hourly.get('temperature_2m', [])
                times = hourly.get('time', [])
                
                if temps:
                    success_count += 1
                    for t_idx, val in enumerate(temps):
                        if val is None: continue
                        curr_t = datetime.fromisoformat(times[t_idx])
                        if start_utc <= curr_t <= end_utc:
                            if val < g_min["val"]:
                                g_min = {"val": val, "city": batch[idx]['name'], "time": times[t_idx]}
                            if val > g_max["val"]:
                                g_max = {"val": val, "city": batch[idx]['name'], "time": times[t_idx]}
        except: continue

    return g_min, g_max, success_count

# --- 3. DASHBOARD ---
st.title("ICON-EU Direct DWD Scanner v40.0")
st.markdown("Közvetlen hozzáférés a Német Időjárási Szolgálat (DWD) modelljéhez.")

target_day = st.date_input("Céldátum:", value=datetime(2026, 1, 9))

if st.button("ORSZÁGOS ICON-EU KERESÉS INDÍTÁSA"):
    with st.spinner("Kapcsolódás a DWD adatbázishoz (3155 pont)..."):
        n_min, n_max, count = run_direct_dwd_scan(target_day)

    if count == 0:
        st.error("A DWD szerverei még nem tölthették fel a január 9-i adatokat, vagy a koordinátákra nincs válasz.")
        st.info("Próbáljuk meg január 7-re vagy 8-ra az ellenőrzéshez!")
    else:
        st.success(f"Sikeres lekérdezés: {count} település adatai beérkeztek.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
                <div class="result-card">
                    <span class="source-tag">ICON-EU MINIMUM</span>
                    <div class="temp-val">{round(n_min['val'], 1)} °C</div>
                    <div class="city-label">📍 {n_min['city']}</div>
                    <div style="color:#ef4444; font-weight:bold; margin-top:10px;">{n_min['time'].replace('T', ' ')} UTC</div>
                </div>
            """, unsafe_allow_html=True)
        
        with c2:
            st.markdown(f"""
                <div class="result-card" style="border-top-color:#dc2626;">
                    <span class="source-tag" style="background:#fee2e2; color:#dc2626;">ICON-EU MAXIMUM</span>
                    <div class="temp-val" style="color:#dc2626;">{round(n_max['val'], 1)} °C</div>
                    <div class="city-label">📍 {n_max['city']}</div>
                    <div style="color:#ef4444; font-weight:bold; margin-top:10px;">{n_max['time'].replace('T', ' ')} UTC</div>
                </div>
            """, unsafe_allow_html=True)
