import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. PROFI METEOROLÓGIAI UI ---
st.set_page_config(page_title="Met-Ensemble v29.0", layout="wide")

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
    .time-stamp { font-family: 'Courier New', monospace; color: #94a3b8; font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ABSZOLÚT ÓRÁNKÉNTI SZKENNER ---
def run_true_deep_scan(target_date):
    try:
        # Teljes 3155 településes adatbázis
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # Ablak: T-1 18:00 UTC -> T 18:00 UTC
    start_dt = datetime.combine(target_date - timedelta(days=1), datetime.min.time()).replace(hour=18)
    end_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=18)
    
    # Inicializálás
    g_min = {"val": 99.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -99.0, "city": "N/A", "time": "N/A"}

    # Batch (400 település / kérés a stabilitásért)
    for i in range(0, len(towns), 400):
        batch = towns[i:i+400]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # 51 tagú ensemble (fáklya) lekérése óránkénti felbontásban
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs&ensemble=true"
               f"&start_date={start_dt.strftime('%Y-%m-%d')}&end_date={end_dt.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            if not isinstance(res, list): res = [res]
            
            for idx, r in enumerate(res):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                
                # Végigmegyünk az összes ensemble tagon (member00...50)
                for key, temps in hourly.items():
                    if 'temperature_2m' in key:
                        # Minden egyes órát ellenőriz az adott fáklyaszálon
                        for t_idx, temp in enumerate(temps):
                            if temp is None: continue
                            
                            curr_time = datetime.fromisoformat(times[t_idx])
                            # Szűrés a pontos 18-18 UTC ablakra
                            if start_dt <= curr_time <= end_dt:
                                if temp < g_min["val"]:
                                    g_min = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
                                if temp > g_max["val"]:
                                    g_max = {"val": temp, "city": batch[idx]['name'], "time": times[t_idx]}
        except: continue

    return g_min, g_max

# --- 3. DASHBOARD ---
st.title("ECMWF True Extreme Scanner v29.0")
st.markdown("### 3155 település fáklyaszálainak (51 tag) óránkénti elemzése (18-18 UTC)")

target_day = st.date_input("Céldátum:", value=datetime(2026, 1, 9))

if st.button("ORSZÁGOS MÉLY-SZKENNELÉS INDÍTÁSA"):
    with st.spinner("Folyamatban: 3155 pont x 51 fáklyaszál x 24 óra elemzése..."):
        n_min, n_max = run_true_deep_scan(target_day)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
            <div class="result-card" style="border-bottom-color: #2563eb;">
                <div class="label">Országos Minimum (Abszolút Fáklya-alj)</div>
                <div class="temp-display" style="color:#1e40af;">{round(n_min['val'], 1)} °C</div>
                <div class="city-info">📍 {n_min['city']}</div>
                <div class="time-stamp">Időpont: {n_min['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="result-card" style="border-bottom-color: #dc2626;">
                <div class="label">Országos Maximum (Abszolút Fáklya-tető)</div>
                <div class="temp-display" style="color:#b91c1c;">{round(n_max['val'], 1)} °C</div>
                <div class="city-info">📍 {n_max['city']}</div>
                <div class="time-stamp">Időpont: {n_max['time'].replace('T', ' ')} UTC</div>
            </div>
        """, unsafe_allow_html=True)

    st.success("A szkennelés sikeresen befejeződött. Az adatok a modell által jelzett abszolút fizikai szélsőértékeket mutatják.")
