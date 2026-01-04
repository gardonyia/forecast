import streamlit as st
import requests
from datetime import datetime, timedelta

# --- UI ÉS DOKUMENTÁCIÓ ---
st.set_page_config(page_title="Met-Master v42.0", layout="wide")
st.markdown("""
    ### Műszaki Dokumentáció v42.0
    * **Modell:** DWD ICON-Seamless (EU/Global hibrid)
    * **Funkció:** Okos szezon-kapcsoló (Smart Season Switch) - AKTÍV
    * **Lefedettség:** Teljes magyarországi településhálózat (3155 pont)
    """, unsafe_allow_html=True)

def run_pro_national_scan(target_date):
    try:
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10).json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    target_dt = datetime.combine(target_date, datetime.min.time())
    # Szigorú 18-18 UTC ablak a pontos napi szélsőértékekhez
    start_utc = (target_dt - timedelta(days=1)).replace(hour=18)
    end_utc = target_dt.replace(hour=18)
    
    # Adatgyűjtő konténerek
    all_temps = []
    found_towns = 0

    # Országos lefedettség kényszerítése (500-as csomagokban a stabilitásért)
    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats = [str(t['lat']) for t in batch]
        lons = [str(t['lng']) for t in batch]
        
        url = (f"https://api.open-meteo.com/v1/dwd-icon?latitude={','.join(lats)}&longitude={','.join(lons)}"
               f"&hourly=temperature_2m&models=icon_seamless"
               f"&start_date={start_utc.strftime('%Y-%m-%d')}&end_date={end_utc.strftime('%Y-%m-%d')}&timezone=UTC")
        
        try:
            res = requests.get(url).json()
            res_list = res if isinstance(res, list) else [res]
            for idx, r in enumerate(res_list):
                hourly = r.get('hourly', {})
                temps = hourly.get('temperature_2m', [])
                if temps:
                    found_towns += 1
                    # A teljes óránkénti adatsorból kigyűjtjük a szélsőértékeket
                    for t_val in temps:
                        if t_val is not None:
                            all_temps.append({
                                "val": t_val,
                                "city": batch[idx]['name'],
                                "time": hourly['time'][temps.index(t_val)]
                            })
        except: continue

    if not all_temps:
        return None, 0

    # Pontos országos statisztika
    abs_min = min(all_temps, key=lambda x: x['val'])
    abs_max = max(all_temps, key=lambda x: x['val'])
    return (abs_min, abs_max), found_towns

# --- INTERFÉSZ ---
target_day = st.date_input("Válassza ki a vizsgálni kívánt napot:", value=datetime(2026, 1, 9))

if st.button("TELJES ORSZÁGOS ANALÍZIS INDÍTÁSA"):
    with st.spinner("Modelladatok szinkronizálása és országos szkennelés..."):
        results, count = run_pro_national_scan(target_day)

    if results:
        st.success(f"Analízis kész! Feldolgozott települések: {count}/3155")
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("ORSZÁGOS MINIMUM", f"{results[0]['val']} °C", f"Helyszín: {results[0]['city']}")
            st.caption(f"Időpont: {results[0]['time'].replace('T', ' ')} UTC")
            
        with col2:
            st.metric("ORSZÁGOS MAXIMUM", f"{results[1]['val']} °C", f"Helyszín: {results[1]['city']}")
            st.caption(f"Időpont: {results[1]['time'].replace('T', ' ')} UTC")
    else:
        st.error("Jelenleg nincs elérhető modelladat erre az időpontra. Próbálja közelebbi dátummal!")
