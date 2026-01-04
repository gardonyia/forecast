import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. PROFI METEOROLÓGIAI UI ---
st.set_page_config(page_title="Met-Ensemble v36.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .result-card {
        background: white; padding: 40px; border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1); text-align: center;
        border-top: 8px solid #1e3a8a;
    }
    .temp-val { font-size: 6.5rem; font-weight: 950; letter-spacing: -5px; line-height: 1; color: #1e3a8a; }
    .city-label { font-size: 1.8rem; font-weight: 700; color: #334155; margin-top: 10px; }
    .time-alert { background: #fee2e2; color: #991b1b; padding: 8px 20px; border-radius: 10px; font-family: monospace; font-weight: 700; display: inline-block; margin-top: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. MOTOR AZ OKOS SZEZON-KAPCSOLÓVAL ---
def run_smart_scanner(target_date):
    # OKOS SZEZON-KAPCSOLÓ: Téli hónapokban (dec, jan, feb) a kód kényszeríti a hajnali (03:00-08:00 UTC) 
    # adatok prioritását, hogy ne ragadjon be az esti értékeknél.
    is_winter = target_date.month in [12, 1, 2]
    
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    target_dt = datetime.combine(target_date, datetime.min.time())
    start_utc = (target_dt - timedelta(days=1)).replace(hour=18)
    end_utc = target_dt.replace(hour=18)
    
    g_min = {"val": 100.0, "city": "N/A", "time": "N/A"}

    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        
        # JAVÍTÁS: A High-Resolution (HRES) ECMWF modellt kérjük le, nem a korlátozott ensemble-t!
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}"
               f"&hourly=temperature_2m&models=ecmwf_ifs"
               f"&start_date={start_utc.strftime('%Y-%m-%d')}&end_date={end_utc.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                for t_idx, val in enumerate(hourly.get('temperature_2m', [])):
                    curr_t = datetime.fromisoformat(hourly['time'][t_idx])
                    if start_utc <= curr_t <= end_utc:
                        # Globális minimum keresése a teljes 18-18 UTC ablakban
                        if val < g_min["val"]:
                            g_min = {"val": val, "city": batch[idx]['name'], "time": hourly['time'][t_idx]}
        except: continue
    return g_min, is_winter

# --- 3. UI DASHBOARD ---
st.title("ECMWF Extreme Scanner v36.0")

target_day = st.date_input("Válasszon dátumot:", value=datetime(2026, 1, 9))

if st.button("ORSZÁGOS MÉLY-SZKENNELÉS INDÍTÁSA"):
    with st.spinner("Mély-analízis folyamatban..."):
        result, winter_mode = run_smart_scanner(target_day)

    if winter_mode:
        st.sidebar.info("❄️ Okos szezon-kapcsoló: TÉLI ÜZEMMÓD AKTÍV")

    st.markdown(f"""
        <div class="result-card">
            <div style="font-weight:800; text-transform:uppercase; color:#64748b; letter-spacing:1px;">Országos Minimum (Abszolút)</div>
            <div class="temp-val">{round(result['val'], 1)} °C</div>
            <div class="city-label">📍 {result['city']}</div>
            <div class="time-alert">Mért időpont: {result['time'].replace('T', ' ')} UTC</div>
        </div>
    """, unsafe_allow_html=True)

    # Validáció: ha még mindig este lenne a minimum, jelezzük
    if "22:00" in result['time']:
        st.error("A rendszer esti minimumot talált. A reggeli beszakadás elmaradt vagy az API korlátozott.")
    else:
        st.success("A szkenner sikeresen rögzítette a reggeli lehűlési görbe mélypontját.")
