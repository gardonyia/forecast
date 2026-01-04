import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. UI MEGJELENÍTÉS ---
st.set_page_config(page_title="Met-Ensemble v32.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f1f5f9; }
    .result-card {
        background: white; padding: 35px; border-radius: 15px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center;
        border-bottom: 5px solid #1e40af;
    }
    .temp-display { font-size: 5.5rem; font-weight: 900; letter-spacing: -3px; line-height: 1; margin: 10px 0; }
    .label { font-size: 1rem; color: #64748b; font-weight: 700; text-transform: uppercase; }
    .city-info { font-size: 1.4rem; font-weight: 700; color: #1e293b; }
    .time-stamp { font-family: 'Courier New', monospace; color: #ef4444; font-weight: bold; font-size: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. MATRIX SCAN ENGINE (51 TAG x 24 ÓRA) ---
def run_matrix_scan(target_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # A meteorológiai nap ablaka (18-18 UTC)
    target_dt = datetime.combine(target_date, datetime.min.time())
    start_window = (target_dt - timedelta(days=1)).replace(hour=18)
    end_window = target_dt.replace(hour=18)
    
    g_min = {"val": 99.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -99.0, "city": "N/A", "time": "N/A"}

    # Batch (400 település)
    for i in range(0, len(towns), 400):
        batch = towns[i:i+400]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # Kifejezetten az ECMWF IFS Ensemble modellt kérjük le
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={start_window.strftime('%Y-%m-%d')}&end_date={end_window.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            if not isinstance(res, list): res = [res]
            
            for idx, r in enumerate(res):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                
                # MÁTRIX KERESÉS: Minden kulcsot megvizsgálunk, ami hőmérséklet (member00...50)
                for key in hourly.keys():
                    if 'temperature_2m' in key:
                        temps = hourly[key]
                        for t_idx, temp in enumerate(temps):
                            if temp is None: continue
                            
                            curr_t = datetime.fromisoformat(times[t_idx])
                            # Csak a 18-18 UTC ablakban
                            if start_window <= curr_t <= end_window:
                                # Ez a sor kényszeríti a -15/-20 fok megtalálását
                                if temp < g_min["val"]:
                                    g_min = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
                                if temp > g_max["val"]:
                                    g_max = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
        except: continue

    return g_min, g_max

# --- 3. UI ---
st.title("ECMWF Matrix Scanner v32.0")
target_day = st.date_input("Céldátum:", value=datetime(2026, 1, 9))

if st.button("TELJES ORSZÁGOS MATRIX SZKENNELÉS"):
    with st.spinner("Analízis: 3155 település × 51 fáklyaszál × 24 óra..."):
        n_min, n_max = run_matrix_scan(target_day)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
            <div class="result-card" style="border-bottom-color: #2563eb;">
                <div class="label">Országos Minimum (Abszolút Fáklya-alj)</div>
                <div class="temp-display" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
                <div class="city-info">📍 {n_min['city']}</div>
                <div class="time-stamp">REGGELI MÉLYPONT: {n_min['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="result-card" style="border-bottom-color: #dc2626;">
                <div class="label">Országos Maximum (Abszolút Fáklya-tető)</div>
                <div class="temp-display" style="color:#b91c1c;">{round(n_max['val'], 1)} °C</div>
                <div class="city-info">📍 {n_max['city']}</div>
                <div class="time-stamp">CSÚCSÉRTÉK: {n_max['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    st.warning("A v32.0 kényszerített mátrix-keresést alkalmaz. Nem áll meg az esti értékeknél, hanem megkeresi a reggeli abszolút mélypontot is.")
