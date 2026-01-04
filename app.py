import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- 1. UI/UX KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-Ensemble Pro v18.0", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .main .block-container { max-width: 1100px; padding-top: 1rem; }
    .data-card {
        background: #1e293b; padding: 24px; border-radius: 8px;
        border: 1px solid #334155; text-align: left;
    }
    .main-temp { font-size: 4rem; font-weight: 900; line-height: 1; letter-spacing: -2px; margin: 10px 0; }
    .tech-box {
        background: #0f172a; border-left: 4px solid #3b82f6;
        padding: 15px; font-family: monospace; font-size: 0.85rem; color: #94a3b8;
    }
    .status-badge {
        padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; font-weight: 800;
        text-transform: uppercase; background: #334155; color: #94a3b8;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. OKOS SZEZON-KAPCSOLÓ ÉS LOGIKA ---
def get_system_config(target_date):
    month = target_date.month
    # Okos szezon-kapcsoló logika
    is_winter = month in [11, 12, 1, 2, 3]
    return {
        "is_winter": is_winter,
        "mode": "WINTER_VALLEY_LOGIC" if is_winter else "SUMMER_UHI_LOGIC",
        "zabar_factor": -2.5,  # Fix korrekció
        "threshold": -13,
        "bias": 0.95  # 95%-os eltolás az extrém hideg felé
    }

# --- 3. DINAMIKUS ANALÍZIS ENGINE ---
def run_analysis(target_date, cfg):
    # Modell súlyozás rácsfelbontás alapján
    weights = {"ecmwf_ifs": 0.40, "icon_eu": 0.45, "gfs_seamless": 0.15}
    
    try:
        # Teljes magyar településlista lekérése
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Zabar", "lat": 48.15, "lng": 20.25}, {"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    # Időablak beállítása (UTC)
    t_start = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_end = target_date.strftime('%Y-%m-%d')
    
    all_results = []
    
    # Kötegelt lekérdezés (800 település / kérés a sebességért)
    for i in range(0, len(towns), 800):
        batch = towns[i:i+800]
        lats = [t['lat'] for t in batch]
        lons = [t['lng'] for t in batch]
        df = pd.DataFrame([{"n": t['name'], "min": 0.0, "max": 0.0, "raw": []} for t in batch])

        for m_id, w in weights.items():
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_start}&end_date={t_end}&timezone=UTC"
                res = requests.get(url).json()
                res_list = res if isinstance(res, list) else [res]
                
                for idx, r in enumerate(res_list):
                    temps = [t for t in r.get('hourly', {}).get('temperature_2m', []) if t is not None]
                    if temps:
                        t_min = min(temps)
                        df.at[idx, "min"] += t_min * w
                        df.at[idx, "max"] += max(temps) * w
                        df.at[idx, "raw"].append(t_min)
            except: pass

        # --- EXTRÉM KORREKCIÓ ÉS VÖLGY-DINAMIKA ---
        for idx in range(len(df)):
            if df.at[idx, "raw"]:
                abs_min = min(df.at[idx, "raw"])
                if cfg["is_winter"] and abs_min < -5:
                    # Elhagyjuk az átlagot, a leghidegebb modell dominál (95%)
                    df.at[idx, "min"] = (df.at[idx, "min"] * 0.05) + (abs_min * 0.95)
                    # Zabar-faktor alkalmazása szélsőség esetén
                    if abs_min < cfg["threshold"]:
                        df.at[idx, "min"] += cfg["zabar_factor"]
                elif not cfg["is_winter"] and df.at[idx, "min"] > 18:
                    df.at[idx, "min"] += 2.2 # Városi hősziget (UHI)
        
        all_results.append(df)
    
    return pd.concat(all_results)

# --- 4. INTERAKTÍV FELÜLET ---
st.title("MET-ENSEMBLE PRO // COMMAND CENTER")

# Dátumválasztó - Ez indítja el a futtatást
selected_date = st.date_input("VÁLASSZON DÁTUMOT AZ ELEMZÉSHEZ:", value=datetime(2026, 1, 9))
config = get_system_config(selected_date)

st.write("---")

with st.spinner(f"ANALYZING DATA FOR {selected_date}..."):
    results = run_analysis(selected_date, config)
    res_min = results.loc[results['min'].idxmin()]
    res_max = results.loc[results['max'].idxmax()]

# Megjelenítés
col1, col2 = st.columns(2)

with col1:
    st.markdown(f"""
    <div class="data-card">
        <span class="status-badge" style="color:#60a5fa">National Minimum</span>
        <div class="main-temp" style="color:#60a5fa">{round(res_min['min'], 1)}°C</div>
        <div style="color:#94a3b8; font-weight:600;">📍 {res_min['n']}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="data-card">
        <span class="status-badge" style="color:#f87171">National Maximum</span>
        <div class="main-temp" style="color:#f87171">{round(res_max['max'], 1)}°C</div>
        <div style="color:#94a3b8; font-weight:600;">📍 {res_max['n']}</div>
    </div>
    """, unsafe_allow_html=True)

# Technikai napló
st.write("<br>", unsafe_allow_html=True)
st.subheader("SYSTEM LOG & DOCUMENTATION")
st.markdown(f"""
<div class="tech-box">
    <b>[LOG_MODE]:</b> {config['mode']} aktív.<br>
    <b>[ZABAR_FACTOR]:</b> {config['zabar_factor']}°C korrekció alkalmazva {config['threshold']}°C alatt.<br>
    <b>[VALLY_DYNAMICS]:</b> 95% súlyozás a leghidegebb modell-rácspontra (Bias: {config['bias']}).<br>
    <b>[ENSEMBLE]:</b> ICON-EU (45%), ECMWF (40%), GFS (15%).
</div>
""", unsafe_allow_html=True)
