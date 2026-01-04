import streamlit as st
import requests
from datetime import datetime, timedelta

# --- 1. UI DESIGN ---
st.set_page_config(page_title="Met-ICON v38.0", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f1f5f9; }
    .main-card {
        background: white; padding: 40px; border-radius: 20px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05); text-align: center;
        border-top: 6px solid #0369a1;
    }
    .temp-val { font-size: 6rem; font-weight: 900; color: #0369a1; letter-spacing: -3px; line-height: 1; }
    .city-info { font-size: 1.8rem; font-weight: 700; color: #334155; margin-top: 10px; }
    .badge { background: #e0f2fe; color: #0369a1; padding: 5px 15px; border-radius: 15px; font-weight: 700; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ICON-EU CORE ENGINE ---
def run_icon_pure_scan(target_date):
    # Településlista betöltése
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # Időablak beállítása (18-18 UTC)
    target_dt = datetime.combine(target_date, datetime.min.time())
    start_utc = (target_dt - timedelta(days=1)).replace(hour=18)
    end_utc = target_dt.replace(hour=18)
    
    g_min = {"val": 100.0, "city": "N/A", "time": "N/A"}
    g_max = {"val": -100.0, "city": "N/A", "time": "N/A"}
    processed_count = 0

    # Kötegelt lekérdezés az ICON-EU modellel
    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats = [str(t['lat']) for t in batch]
        lons = [str(t['lng']) for t in batch]
        
        # KIZÁRÓLAG ICON-EU MODELL
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={','.join(lats)}&longitude={','.join(lons)}"
               f"&hourly=temperature_2m&models=icon_eu"
               f"&start_date={start_utc.strftime('%Y-%m-%d')}&end_date={end_utc.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                times = hourly.get('time', [])
                temps = hourly.get('temperature_2m_icon_eu', []) # ICON-EU specifikus kulcs
                
                if temps:
                    processed_count += 1
                    for t_idx, val in enumerate(temps):
                        if val is None: continue
                        curr_t = datetime.fromisoformat(times[t_idx])
                        
                        if start_utc <= curr_t <= end_utc:
                            if val < g_min["val"]:
                                g_min = {"val": val, "city": batch[idx]['name'], "time": times[t_idx]}
                            if val > g_max["val"]:
                                g_max = {"val": val, "city": batch[idx]['name'], "time": times[t_idx]}
        except:
            continue

    return g_min, g_max, processed_count

# --- 3. UI ---
st.title("ICON-EU Magyarországi Szélsőérték Szkenner")
st.info("Ez a verzió kizárólag a német ICON-EU modell adatait használja, mindenféle szezonális korrekció nélkül.")

target_day = st.date_input("Válasszon dátumot (január 9 javasolt):", value=datetime(2026, 1, 9))

if st.button("TELJES ORSZÁGOS ICON-EU ANALÍZIS"):
    with st.spinner("3155 település ICON-EU adatainak lekérése..."):
        n_min, n_max, count = run_icon_pure_scan(target_day)

    st.write(f"Sikeresen feldolgozott települések száma: **{count}**")

    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
            <div class="main-card">
                <div style="font-weight:800; color:#64748b; text-transform:uppercase;">ICON-EU Országos Minimum</div>
                <div class="temp-val">{round(n_min['val'], 1)} °C</div>
                <div class="city-info">📍 {n_min['city']}</div>
                <div style="margin-top:15px;"><span class="badge">{n_min['time'].replace('T', ' ')} UTC</span></div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="main-card" style="border-top-color:#be123c;">
                <div style="font-weight:800; color:#64748b; text-transform:uppercase;">ICON-EU Országos Maximum</div>
                <div class="temp-val" style="color:#be123c;">{round(n_max['val'], 1)} °C</div>
                <div class="city-info">📍 {n_max['city']}</div>
                <div style="margin-top:15px;"><span class="badge" style="background:#fff1f2; color:#be123c;">{n_max['time'].replace('T', ' ')} UTC</span></div>
            </div>
        """, unsafe_allow_html=True)

    if count < 3000:
        st.warning("Néhány településnél nem állt rendelkezésre ICON-EU adat, de az összesített szélsőértékek a rendelkezésre álló adatokból készültek.")
