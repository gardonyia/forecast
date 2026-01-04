import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. UI KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-Ensemble Pro v12.0", layout="wide")

st.markdown("""
    <style>
    .main .block-container { max-width: 95%; padding-top: 1rem; }
    .result-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border-top: 5px solid #2563eb; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; margin-bottom: 20px; }
    .methu-link-card { background-color: #f0fdf4; border: 1px dashed #16a34a; padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 20px; }
    .tech-card { background-color: #f8fafc; padding: 20px; border-radius: 8px; border-left: 6px solid #334155; margin-bottom: 15px; line-height: 1.6; }
    .tech-title { font-weight: bold; color: #1e293b; text-transform: uppercase; font-size: 0.9rem; letter-spacing: 0.5px; display: block; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. OKOS SZEZON-KAPCSOLÓ ÉS PARAMÉTEREZÉS ---
def get_seasonal_logic(target_date):
    month = target_date.month
    # Téli félév (Nov-Márc): Fagyzug fókusz
    if month in [11, 12, 1, 2, 3]:
        return {
            "mode": "TÉLI (Inverziós)",
            "factor_name": "Zabar-faktor",
            "threshold": -13,
            "adj": -2.5,
            "color": "#1e40af",
            "detail": "A fókusz a negatív irányú anomáliák (völgyhűlés) detektálásán van."
        }
    # Nyári félév (Ápr-Okt): Hősziget fókusz
    else:
        return {
            "mode": "NYÁRI (Konvektív)",
            "factor_name": "UHI-faktor",
            "threshold": 18,
            "adj": 2.2,
            "color": "#b91c1c",
            "detail": "A fókusz a pozitív irányú anomáliák (városi hősziget) kezelésén van."
        }

# --- 3. MEGBÍZHATÓSÁGI SÚLYOZÁS ---
def get_static_ensemble_weights():
    # A modellek történelmi és rácsfelbontás alapú súlyozása
    return {
        "ecmwf_ifs": 0.45,  # 9km felbontás, legjobb globális készség
        "icon_eu": 0.35,    # 6.7km felbontás, kiváló lokális dinamika
        "gfs_seamless": 0.20 # 13km felbontás, korrekciós réteg
    }

# --- 4. SZÁMÍTÁSI MOTOR ---
def run_national_analysis(target_date, weights, config):
    try:
        r = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=5)
        towns = r.json()
    except:
        towns = [{"name": "Budapest", "lat": 47.49, "lng": 19.04}, {"name": "Zabar", "lat": 48.15, "lng": 20.25}]

    t_s, t_e = (target_date - timedelta(days=1)).strftime('%Y-%m-%d'), target_date.strftime('%Y-%m-%d')
    all_results = []

    for i in range(0, len(towns), 500):
        batch = towns[i:i+500]
        lats, lons = [t.get('lat', 47) for t in batch], [t.get('lng', 19) for t in batch]
        df = pd.DataFrame([{"n": t['name'], "min": 0.0, "max": 0.0} for t in batch])
        raw_mins = []

        for m_id, w in weights.items():
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_s}&end_date={t_e}&timezone=UTC"
                res = requests.get(url).json()
                res_list = res if isinstance(res, list) else [res]
                
                m_batch_mins = []
                for idx, r in enumerate(res_list):
                    t_data = [t for t in r.get('hourly', {}).get('temperature_2m', []) if t is not None]
                    if t_data:
                        df.at[idx, "min"] += min(t_data) * w
                        df.at[idx, "max"] += max(t_data) * w
                        m_batch_mins.append(min(t_data))
                    else: m_batch_mins.append(None)
                raw_mins.append(m_batch_mins)
            except: raw_mins.append([None]*len(batch))

        # --- SZEZONÁLIS ANOMÁLIA KEZELÉS ---
        for idx in range(len(df)):
            valid_mins = [m[idx] for m in raw_mins if idx < len(m) and m[idx] is not None]
            if valid_mins:
                local_min = min(valid_mins)
                if config['mode'].startswith("TÉLI"):
                    # 1. Lépcső: Dinamikus inverziós súlyozás -7 fok alatt
                    if local_min < -7:
                        df.at[idx, "min"] = (df.at[idx, "min"] * 0.25) + (local_min * 0.75)
                    # 2. Lépcső: Zabar-faktor korrekció -13 fok alatt
                    if local_min < config['threshold']:
                        df.at[idx, "min"] += config['adj']
                else:
                    # Nyári hősziget korrekció
                    if local_min > config['threshold']:
                        df.at[idx, "min"] += config['adj']
        
        all_results.append(df)
    return pd.concat(all_results)

# --- 5. DASHBOARD MEGJELENÍTÉS ---
target_date = st.date_input("Céldátum választása:", value=datetime.now().date() + timedelta(days=1))
config = get_seasonal_logic(target_date)
weights = get_static_ensemble_weights()

col_main, col_tech = st.columns([1.8, 1.2], gap="large")

with col_main:
    st.subheader(f"🌡️ Modell-Ensemble ({config['mode']})")
    st.markdown(f'<div class="methu-link-card">Hivatalos MET.HU előrejelzés: <a href="https://www.met.hu/idojaras/elorejelzes/magyarorszag/" target="_blank">Kattints IDE</a></div>', unsafe_allow_html=True)

    with st.spinner("Nemzeti adatbázis feldolgozása..."):
        data = run_national_analysis(target_date, weights, config)
        res_min = data.loc[data['min'].idxmin()]
        res_max = data.loc[data['max'].idxmax()]

    c1, c2 = st.columns(2)
    c1.markdown(f'<div class="result-card"><span class="tech-title">Országos Minimum</span><h1 style="color:{config["color"]};">{round(res_min["min"], 1)} °C</h1>📍 {res_min["n"]}</div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="result-card"><span class="tech-title">Országos Maximum</span><h1 style="color:#b91c1c;">{round(res_max["max"], 1)} °C</h1>📍 {res_max["n"]}</div>', unsafe_allow_html=True)

with col_tech:
    st.subheader("⚙️ Részletes Technikai Dokumentáció")
    
    st.markdown(f"""
    <div class="tech-card">
        <span class="tech-title">1. Okos Szezon-kapcsoló</span>
        A rendszer egy naptári alapú algoritmust használ (Nov-Márc / Ápr-Okt). Télen a <b>kisugárzási hűlés</b>, nyáron a <b>városi hősziget</b> (UHI) dominál. A váltás automatikus, a technikai paraméterek (küszöb, adjusztáció) a dátumhoz igazodnak.
    </div>

    <div class="tech-card">
        <span class="tech-title">2. Dinamikus Zabar-faktor ({config['adj']} °C)</span>
        A téli üzemmódban a globális modellek domborzati elsimítását (smoothing) korrigáljuk. 
        - <b>Küszöb:</b> -13 °C alatt aktiválódik.<br>
        - <b>Mechanizmus:</b> A súlyozott átlaghoz képest fix 2,5 fokos negatív degressziót alkalmazunk a mélyebben fekvő rácspontokon.
    </div>

    <div class="tech-card">
        <span class="tech-title">3. Megbízhatósági Súlyozás (MME)</span>
        A korábbi bizonytalan múltbeli validáció helyett <b>Multi-Model Ensemble</b> súlyozást használunk:<br>
        • <b>ECMWF (45%):</b> Globális stabilitás.<br>
        • <b>ICON-EU (35%):</b> Nagy felbontású európai dinamika.<br>
        • <b>GFS (20%):</b> Korrekciós statisztikai réteg.
    </div>

    <div class="tech-card">
        <span class="tech-title">4. Kárpát-medencei Inverziós Modul</span>
        -7 °C alatt a rendszer érzékeli a stabil rétegződést. Ekkor a súlyozott átlag helyett a <b>legvadabb (leghidegebb) modell</b> 75%-os súlyt kap, mivel a tapasztalat szerint extrém helyzetekben a konzervatív átlagolás alábecsüli a lehűlést.
    </div>
    """, unsafe_allow_html=True)

    st.plotly_chart(px.pie(values=list(weights.values()), names=["ECMWF", "ICON", "GFS"], hole=0.6).update_layout(height=180, margin=dict(l=0,r=0,b=0,t=0), showlegend=False))
