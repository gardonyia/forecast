import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. PROFI UI KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-Ensemble v33.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    .result-card {
        background: white; padding: 40px; border-radius: 20px;
        box-shadow: 0 15px 35px rgba(0,0,0,0.15); text-align: center;
        border: 2px solid #cbd5e1;
    }
    .temp-val { font-size: 6.5rem; font-weight: 950; letter-spacing: -6px; line-height: 1; margin: 10px 0; }
    .label { font-size: 1.1rem; color: #475569; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }
    .city-info { font-size: 1.8rem; font-weight: 700; color: #0f172a; margin-top: 10px; }
    .time-alert { color: #e11d48; font-family: monospace; font-weight: bold; font-size: 1.1rem; background: #fff1f2; padding: 5px 15px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. MULTI-MEMBER EXTREME SCANNER ---
def run_absolute_recovery(target_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # Ablak szigorúan: T-1 18:00 UTC - T 18:00 UTC
    target_dt = datetime.combine(target_date, datetime.min.time())
    start_utc = (target_dt - timedelta(days=1)).replace(hour=18)
    end_utc = target_dt.replace(hour=18)
    
    g_min = {"val": 100.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -100.0, "city": "N/A", "time": "N/A"}

    # Kötegelt lekérdezés (350 település / kérés a stabilitásért)
    for i in range(0, len(towns), 350):
        batch = towns[i:i+350]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # EXPLICIT ENSEMBLE KÉRÉS: Minden tagot lekérünk óránként
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={start_utc.strftime('%Y-%m-%d')}&end_date={end_utc.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            # Ha több helyszín van, az API listát ad vissza
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                
                # Átvizsgáljuk az összes lehetséges member-szálat (member00-tól member50-ig)
                # Az Open-Meteo ezeket temperature_2m_member00 formátumban adja
                for key in hourly.keys():
                    if 'temperature_2m' in key:
                        temps = hourly[key]
                        for t_idx, val in enumerate(temps):
                            if val is None: continue
                            
                            curr_t = datetime.fromisoformat(times[t_idx])
                            # Szigorú időablak ellenőrzés
                            if start_utc <= curr_t <= end_utc:
                                # Ez a mag: ha találunk hidegebbet bárhol, bármelyik szálon, frissítünk
                                if val < g_min["val"]:
                                    g_min = {"val": val, "city": batch[idx]['name'], "time": times[t_idx]}
                                if val > g_max["val"]:
                                    g_max = {"val": val, "city": batch[idx]['name'], "time": times[t_idx]}
        except: continue

    return g_min, g_max

# --- 3. UI DASHBOARD ---
st.title("ECMWF Absolute Recovery Scanner v33.0")
st.markdown("### 3155 pont × 51 fáklyaszál × 24 óra – A fizikai legalja keresése")

target_day = st.date_input("Céldátum:", value=datetime(2026, 1, 9))

if st.button("TELJES ORSZÁGOS ANALÍZIS INDÍTÁSA"):
    with st.spinner("Mély-keresés folyamatban (18-18 UTC ablak)..."):
        n_min, n_max = run_absolute_recovery(target_day)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
            <div class="result-card">
                <div class="label">Országos Minimum (Fáklya legalja)</div>
                <div class="temp-val" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
                <div class="city-info">📍 {n_min['city']}</div>
                <div class="time-alert">Időpont: {n_min['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
            <div class="result-card">
                <div class="label">Országos Maximum (Fáklya teteje)</div>
                <div class="temp-val" style="color:#dc2626;">{round(n_max['val'], 1)} °C</div>
                <div class="city-info">📍 {n_max['city']}</div>
                <div class="time-alert" style="background:#fff7ed; color:#ea580c;">Időpont: {n_max['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    st.info("A v33.0 kényszeríti az összes egyedi ensemble tag (member00-50) óránkénti átvilágítását.")
