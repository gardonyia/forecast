import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Modell-Ensemble Dashboard", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .methodology-box { background-color: #f1f3f9; padding: 25px; border-radius: 15px; border-left: 8px solid #0d6efd; margin-bottom: 20px; }
    .model-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 10px; }
    h3 { color: #0d6efd; }
    </style>
    """, unsafe_allow_html=True)

# --- KONSTANSOK ---
TOP_10_CITIES = [
    {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23},
    {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69},
    {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41},
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}
]

MODELS = ["ecmwf_ifs", "icon_eu", "gfs_seamless"]

# --- DINAMIKUS SÚLYOZÁS SZÁMÍTÁSA ---
@st.cache_data(ttl=3600)
def calculate_dynamic_ensemble():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    validation_results = []
    model_errors = {m: [] for m in MODELS}

    for city in TOP_10_CITIES:
        try:
            # Tényadatok lekérése (Archívum)
            obs_r = requests.get(f"https://archive-api.open-meteo.com/v1/archive?latitude={city['lat']}&longitude={city['lon']}&start_date={yesterday}&end_date={yesterday}&hourly=temperature_2m").json()
            t_min, t_max = min(obs_r['hourly']['temperature_2m']), max(obs_r['hourly']['temperature_2m'])
            
            row = {"Város": city['n'], "Valóság (Min/Max)": f"{t_min} / {t_max} °C"}
            
            for m in MODELS:
                # Modell jóslat lekérése a tegnapi napra
                fc_r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={city['lat']}&longitude={city['lon']}&start_date={yesterday}&end_date={yesterday}&hourly=temperature_2m&models={m}").json()
                p_min, p_max = min(fc_r['hourly']['temperature_2m']), max(fc_r['hourly']['temperature_2m'])
                
                error = (abs(t_min - p_min) + abs(t_max - p_max)) / 2
                model_errors[m].append(max(0.1, error))
                row[f"{m.upper()} jósolt"] = f"{p_min} / {p_max}"
            
            validation_results.append(row)
        except: continue

    # Súlyok kiszámítása (Inverz hibaarány: aki pontosabb, nagyobb súlyt kap)
    avg_errors = {m: np.mean(model_errors[m]) for m in MODELS}
    inv_errors = [1/avg_errors[m] for m in MODELS]
    total_inv = sum(inv_errors)
    weights = {m: inv_errors[i]/total_inv for i, m in enumerate(MODELS)}
    
    return weights, pd.DataFrame(validation_results), avg_errors

# --- ADATLEKÉRÉS A CÉLDÁTUMRA ---
def FETCH_DATA(date, weights, towns, p_bar):
    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')
    results = []
    
    for i in range(0, len(towns), 150): # Gyorsított batch feldolgozás
        p_bar.progress(min(i / len(towns), 1.0))
        batch = towns[i:i+150]
        lats, lons = [t['lat'] for t in batch], [t['lon'] for t in batch]
        
        batch_df = pd.DataFrame([{"n": t['n'], "min": 0.0, "max": 0.0} for t in batch])
        current_mins = []

        for m_id, w in weights.items():
            try:
                r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_s}&end_date={t_e}&timezone=UTC").json()
                res_list = r if isinstance(r, list) else [r]
                
                m_list = []
                for idx, res in enumerate(res_list):
                    temps = res['hourly']['temperature_2m']
                    m_min = min(temps)
                    batch_df.at[idx, "min"] += m_min * w
                    batch_df.at[idx, "max"] += max(temps) * w
                    m_list.append(m_min)
                current_mins.append(m_list)
            except: continue
        
        # Téli extra korrekció
        if current_mins:
            for idx in range(len(batch_df)):
                abs_min = min([m[idx] for m in current_mins])
                if abs_min < -5:
                    batch_df.at[idx, "min"] = (batch_df.at[idx, "min"] * 0.2) + (abs_min * 0.8)
                if abs_min < -12: batch_df.at[idx, "min"] -= 3.0

        results.append(batch_df)
    
    return pd.concat(results, ignore_index=True)

# --- UI ELRENDEZÉS ---
weights, val_df, errors = calculate_dynamic_ensemble()

col_main, col_info = st.columns([2, 1.2], gap="large")

with col_main:
    st.title("🌡️ Modell-Súlyozó Dashboard")
    target_date = st.date_input("Előrejelzés dátuma", datetime.now() + timedelta(days=1))
    
    st.subheader("📊 Multi-Model Validációs Mátrix")
    st.write("A tegnapi nap tényadatai és a modellek jóslatainak összevetése a 10 legnagyobb városban:")
    st.dataframe(val_df, use_container_width=True, hide_index=True)

    # Számítás indítása 3155 településre
    if st.button("🚀 Országos elemzés futtatása (3155 település)"):
        all_towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json").json()
        towns_data = [{"n": d['name'], "lat": float(d['lat']), "lon": float(d['lng'])} for d in all_towns]
        
        p_bar = st.progress(0)
        df = FETCH_DATA(target_date, weights, towns_data, p_bar)
        
        st.write("---")
        m1, m2 = st.columns(2)
        min_r = df.loc[df['min'].idxmin()]
        max_r = df.loc[df['max'].idxmax()]
        
        m1.metric("📉 Országos Minimum", f"{round(min_r['min'], 1)} °C")
        m1.info(f"📍 Helyszín: **{min_r['n']}**")
        
        m2.metric("📈 Országos Maximum", f"{round(max_r['max'], 1)} °C")
        m2.info(f"📍 Helyszín: **{max_r['n']}**")

with col_info:
    st.header("⚙️ Működési Módszertan")
    
    st.markdown(f"""
    <div class="methodology-box">
        <h3>1. Dinamikus Súlyozás (10-Point D-MOS)</h3>
        A rendszer nem egyetlen ponton, hanem az alábbi 10 nagyváros adatain kalibrálja magát:<br>
        <i>Budapest, Debrecen, Szeged, Miskolc, Pécs, Győr, Nyíregyháza, Kecskemét, Székesfehérvár, Szombathely.</i>
        <br><br>
        <b>Kiszámított MAE hibaértékek:</b><br>
        • ECMWF: {round(errors['ecmwf_ifs'], 2)} °C<br>
        • ICON-EU: {round(errors['icon_eu'], 2)} °C<br>
        • GFS: {round(errors['gfs_seamless'], 2)} °C
    </div>
    
    <div class="methodology-box">
        <h3>2. Ensemble Logika</h3>
        A súlyok elosztása az <b>Inverz Hibaarány Elve</b> alapján történik. 
        Aki kisebb hibát vétett a tegnapi napon, az automatikusan nagyobb befolyást kap a mai előrejelzésben.
    </div>

    <div class="methodology-box">
        <h3>3. Téi Fagyzug Algoritmus</h3>
        A globális modellek rácshálója nem látja a magyarországi völgyek mikroklimatikus hűlését. 
        Ezért a rendszer -5°C alatt <b>agresszív szélsőérték-keresést</b> végez, és -12°C alatt extra fizikai hűtési faktort alkalmaz a reális értékek (pl. met.hu szintje) eléréséhez.
    </div>
    """, unsafe_allow_html=True)

    st.write("**Aktuális modellsúlyok:**")
    st.plotly_chart(px.pie(values=list(weights.values()), names=["ECMWF", "ICON-EU", "GFS"], hole=0.6).update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250))
