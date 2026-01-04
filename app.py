import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- 1. UI ÉS UX KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-Ensemble v17.0", layout="wide", page_icon="🌡️")

st.markdown("""
    <style>
    /* Letisztult, modern háttér és betűtípus */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #f8fafc; }
    .main .block-container { max-width: 900px; padding-top: 1.5rem; }
    
    /* Kompakt, elegáns kártyák */
    .mini-card {
        background: white;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }
    .temp-val { font-size: 2.8rem; font-weight: 800; line-height: 1; margin: 8px 0; }
    .loc-label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
    
    /* Szezon jelző pill */
    .season-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 700;
        background: #f1f5f9;
        text-transform: uppercase;
    }
    
    /* Segéd stílusok */
    .stExpander { border: none !important; box-shadow: none !important; background: transparent !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. OKOS SZEZON-KAPCSOLÓ LOGIKA ---
def get_season_config(date):
    month = date.month
    # Okos szezon-kapcsoló (Tél: Nov-Márc)
    is_winter = month in [11, 12, 1, 2, 3]
    return {
        "is_winter": is_winter,
        "mode_label": "TÉLI (Fagyzug Fókusz)" if is_winter else "NYÁRI (Hősziget Fókusz)",
        "zabar_adj": -2.5, # Felhasználói kérésre fixált érték
        "threshold": -13 if is_winter else 18,
        "theme_color": "#1e40af" if is_winter else "#e11d48"
    }

# --- 3. ANALÍZIS ENGINE ---
def run_ensemble_analysis(date, cfg):
    # Rögzített súlyozás a pontosság érdekében
    weights = {"ecmwf_ifs": 0.45, "icon_eu": 0.35, "gfs_seamless": 0.20}
    
    try:
        # 3155 magyar település betöltése
        towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5).json()
    except:
        towns = [{"name": "Zabar", "lat": 48.15, "lng": 20.25}, {"name": "Budapest", "lat": 47.49, "lng": 19.04}]

    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')
    all_results = []

    # Kötegelt feldolgozás a hatékonyságért
    for i in range(0, len(towns), 1000):
        batch = towns[i:i+1000]
        lats, lons = [t['lat'] for t in batch], [t['lng'] for t in batch]
        df = pd.DataFrame([{"n": t['name'], "min": 0.0, "max": 0.0} for t in batch])
        model_mins = []

        for m_id, w in weights.items():
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_s}&end_date={t_e}&timezone=UTC"
                res = requests.get(url).json()
                res_list = res if isinstance(res, list) else [res]
                
                m_batch_mins = []
                for idx, r in enumerate(res_list):
                    t_data = r.get('hourly', {}).get('temperature_2m', [])
                    if t_data:
                        valid_t = [t for t in t_data if t is not None]
                        if valid_t:
                            m_min = min(valid_t)
                            df.at[idx, "min"] += m_min * w
                            df.at[idx, "max"] += max(valid_t) * w
                            m_batch_mins.append(m_min)
                        else: m_batch_mins.append(None)
                    else: m_batch_mins.append(None)
                model_mins.append(m_batch_mins)
            except: model_mins.append([None]*len(batch))

        # --- EXTRÉM KORREKCIÓS MODUL ---
        for idx in range(len(df)):
            valid = [m[idx] for m in model_mins if idx < len(m) and m[idx] is not None]
            if valid:
                abs_min = min(valid)
                if cfg["is_winter"]:
                    # Cold-Bias: Ha egy modell látja a beszakadást, 90%-ban azt követjük
                    if abs_min < (df.at[idx, "min"] - 2.0):
                        df.at[idx, "min"] = (df.at[idx, "min"] * 0.1) + (abs_min * 0.9)
                    # Zabar-faktor: Fix -2.5 fok
                    if abs_min < cfg["threshold"]:
                        df.at[idx, "min"] += cfg["zabar_adj"]
                else:
                    # Nyári hősziget korrekció
                    if df.at[idx, "min"] > cfg["threshold"]:
                        df.at[idx, "min"] += 2.2
        
        all_results.append(df)
    
    return pd.concat(all_results)

# --- 4. DASHBOARD FELÜLET ---
header_left, header_right = st.columns([1, 1])

with header_left:
    st.title("Met-Ensemble Pro")
    target_date = st.date_input("Előrejelzés dátuma", value=datetime(2026, 1, 9))
    cfg = get_season_config(target_date)

with header_right:
    st.markdown(f"""
        <div style='text-align:right; padding-top:60px;'>
            <span class='season-pill' style='color:{cfg['theme_color']}; border: 1px solid {cfg['theme_color']}'>
                {cfg['mode_label']} Aktív
            </span>
        </div>
    """, unsafe_allow_html=True)

st.write("---")

# Számítás
with st.spinner("Modellek szinkronizálása..."):
    data = run_ensemble_analysis(target_date, cfg)
    res_min = data.loc[data['min'].idxmin()]
    res_max = data.loc[data['max'].idxmax()]

# Fő értékek
col_min, col_max = st.columns(2)

with col_min:
    st.markdown(f"""
        <div class="mini-card">
            <div class="loc-label">Országos Minimum</div>
            <div class="temp-val" style="color:{cfg['theme_color']}">{round(res_min['min'], 1)} °C</div>
            <div class="loc-label">📍 {res_min['n']}</div>
        </div>
    """, unsafe_allow_html=True)

with col_max:
    st.markdown(f"""
        <div class="mini-card">
            <div class="loc-label">Országos Maximum</div>
            <div class="temp-val" style="color:#e11d48">{round(res_max['max'], 1)} °C</div>
            <div class="loc-label">📍 {res_max['n']}</div>
        </div>
    """, unsafe_allow_html=True)

st.write("<br>", unsafe_allow_html=True)

# --- TECHNIKAI DOKUMENTÁCIÓ (EXPANDER) ---
with st.expander("⚙️ Technikai Dokumentáció (v17.0)"):
    st.markdown(f"""
    ### Módszertan és Korrekciók
    * **Okos Szezon-kapcsoló:** A rendszer automatikusan vált téli (Fagyzug) és nyári (Hősziget) üzemmód között.
    * **Zabar-faktor:** Téli üzemmódban, ha a minimum {cfg['threshold']} °C alá esik, fix **{cfg['zabar_adj']} °C** korrekciót alkalmazunk a domborzati torzítás ellensúlyozására.
    * **Cold-Bias Algoritmus:** A MET.HU és az Ensemble közötti eltérés minimalizálása érdekében a rendszer 90%-os súllyal követi a leghidegebb modellt, ha az jelentősen eltér az átlagtól.
    * **Adatforrások:** ECMWF IFS (45%), ICON-EU (35%), GFS (20%).
    """)

st.markdown("<div style='text-align:center; color:#94a3b8; font-size:0.7rem;'>Adatforrás: Open-Meteo API | Statisztikai Ensemble Modell v17.0</div>", unsafe_allow_html=True)
