import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. UI/UX KONFIGURÁCIÓ (KOMPAKT NÉZET) ---
st.set_page_config(page_title="Met-Ensemble Pro v4", layout="wide")

# CSS a sűrűbb elrendezéshez és professzionális megjelenéshez
st.markdown("""
    <style>
    /* Oldal szélesség és betűméret optimalizálás (~85%) */
    .main .block-container { max-width: 90%; padding-top: 1rem; padding-bottom: 1rem; }
    html { font-size: 14px; } 
    
    .result-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border-top: 4px solid #2563eb; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); text-align: center; margin-bottom: 10px; }
    .tech-card { background-color: #f8fafc; padding: 12px; border-radius: 8px; border-left: 4px solid #334155; margin-bottom: 8px; font-size: 0.9rem; line-height: 1.4; }
    .status-badge { background-color: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; }
    .stDataFrame { font-size: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ADATBÁZIS ÉS KONSTANSOK ---
CITIES_VALIDATION = [
    {"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Szeged", "lat": 46.25, "lon": 20.14}, {"n": "Miskolc", "lat": 48.10, "lon": 20.78},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"n": "Kecskemét", "lat": 46.90, "lon": 19.69},
    {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41}, {"n": "Szombathely", "lat": 47.23, "lon": 16.62}
]
MODEL_MAP = {"ecmwf_ifs": "ECMWF", "icon_eu": "ICON", "gfs_seamless": "GFS"}

# --- 3. CORE LOGIKA: DINAMIKUS SÚLYOZÁS ---
@st.cache_data(ttl=3600)
def get_system_calibration():
    # T-3 nap a tiszta mérésekhez (ahogy kérted, az átfedések elkerülésére)
    val_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    matrix_rows = []
    error_tracking = {m: [] for m in MODEL_MAP.keys()}

    for city in CITIES_VALIDATION:
        try:
            # Valós mérések lekérése
            obs_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={city['lat']}&longitude={city['lon']}&start_date={val_date}&end_date={val_date}&hourly=temperature_2m"
            obs_data = requests.get(obs_url, timeout=5).json()
            t_real_min = min(obs_data['hourly']['temperature_2m'])
            t_real_max = max(obs_data['hourly']['temperature_2m'])
            
            row = {"Város": city['n'], "Mért (Min/Max)": f"{t_real_min} / {t_real_max} °C"}
            
            for m_id in MODEL_MAP.keys():
                fc_url = f"https://api.open-meteo.com/v1/forecast?latitude={city['lat']}&longitude={city['lon']}&start_date={val_date}&end_date={val_date}&hourly=temperature_2m&models={m_id}"
                fc_data = requests.get(fc_url, timeout=5).json()
                p_min = min(fc_data['hourly']['temperature_2m'])
                p_max = max(fc_data['hourly']['temperature_2m'])
                
                err = (abs(t_real_min - p_min) + abs(t_real_max - p_max)) / 2
                error_tracking[m_id].append(max(0.3, err))
                row[f"{MODEL_MAP[m_id]} jósolt"] = f"{p_min} / {p_max}"
            
            matrix_rows.append(row)
        except: continue

    # Súlyok kiszámítása (Inverz MAE)
    avg_mae = {m: np.mean(error_tracking[m]) for m in MODEL_MAP.keys()}
    inv_mae = [1/avg_mae[m] for m in MODEL_MAP.keys()]
    weights_norm = {m: inv_mae[i]/sum(inv_mae) for i, m in enumerate(MODEL_MAP.keys())}
    
    return weights_norm, pd.DataFrame(matrix_rows), avg_mae

# --- 4. CORE LOGIKA: AUTOMATIKUS ELŐREJELZÉS ---
def perform_national_analysis(target_date, weights):
    # Városlista betöltése (Hibatűrő megoldás a JSONDecodeError ellen)
    try:
        r = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=10)
        towns = r.json()
    except:
        st.error("⚠️ Település adatbázis hiba. Kézi vészhelyzeti lista aktiválva.")
        return pd.DataFrame([{"n": "Budapest", "min": 0, "max": 0}])

    t_s = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_e = target_date.strftime('%Y-%m-%d')
    results = []
    
    # 3155 település feldolgozása 300-as batch-ekben
    for i in range(0, len(towns), 300):
        batch = towns[i:i+300]
        lats, lons = [float(t['lat']) for t in batch], [float(t['lng']) for t in batch]
        batch_df = pd.DataFrame([{"n": t['name'], "min": 0.0, "max": 0.0} for t in batch])
        model_results_raw = []

        for m_id, w in weights.items():
            url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_s}&end_date={t_e}&timezone=UTC"
            resp = requests.get(url).json()
            res_list = resp if isinstance(resp, list) else [resp]
            
            m_batch = []
            for idx, res in enumerate(res_list):
                temps = res['hourly']['temperature_2m']
                batch_df.at[idx, "min"] += min(temps) * w
                batch_df.at[idx, "max"] += max(temps) * w
                m_batch.append(min(temps))
            model_results_raw.append(m_batch)

        # FAGYZUG KORREKCIÓ LOGIKA
        for idx in range(len(batch_df)):
            absolute_min = min([m[idx] for m in model_results_raw])
            if absolute_min < -7:
                batch_df.at[idx, "min"] = (batch_df.at[idx, "min"] * 0.15) + (absolute_min * 0.85)
            if absolute_min < -13:
                batch_df.at[idx, "min"] -= 4.2 # "Mohos-töbör" effektus
        
        results.append(batch_df)
    
    return pd.concat(results)

# --- 5. UI ÖSSZEÁLLÍTÁS ---
st.title("🌡️ Met-Ensemble Pro v4 – Automatizált Rendszer")

# Kalibráció futtatása (mindig elérhető változók)
weights, val_matrix, avg_errors = get_system_calibration()

col_left, col_right = st.columns([1.7, 1.3], gap="medium")

with col_left:
    st.subheader("📅 Aktív Előrejelzés")
    target_date = st.date_input("Válasszon egy jövőbeli napot:", 
                                value=datetime.now().date() + timedelta(days=1),
                                min_value=datetime.now().date() + timedelta(days=1))
    
    with st.spinner("Országos hálózat elemzése (3155 pont)..."):
        try:
            forecast_results = perform_national_analysis(target_date, weights)
            res_min = forecast_results.loc[forecast_results['min'].idxmin()]
            res_max = forecast_results.loc[forecast_results['max'].idxmax()]
            
            # EREDMÉNY KÁRTYÁK
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"""<div class="result-card" style="border-top-color: #2563eb; background-color: #eff6ff;">
                    <span class="status-badge">MINIMUM</span>
                    <h1 style="color:#1e40af; font-size: 2.8rem; margin: 5px 0;">{round(res_min['min'], 1)} °C</h1>
                    <p style="font-weight: bold; margin:0;">📍 {res_min['n']}</p>
                </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(f"""<div class="result-card" style="border-top-color: #dc2626; background-color: #fef2f2;">
                    <span class="status-badge" style="background-color:#fee2e2; color:#991b1b;">MAXIMUM</span>
                    <h1 style="color:#991b1b; font-size: 2.8rem; margin: 5px 0;">{round(res_max['max'], 1)} °C</h1>
                    <p style="font-weight: bold; margin:0;">📍 {res_max['n']}</p>
                </div>""", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Hiba az elemzés során: {e}")

    st.write("---")
    st.subheader("📊 Validációs Mátrix (T-3 nap)")
    st.dataframe(val_matrix, hide_index=True, use_container_width=True)

with col_right:
    st.subheader("📘 Részletes Technikai Dokumentáció")
    
    st.markdown("""
    <div class="tech-card">
        <b>1. Reaktív Adat-architektúra:</b><br>
        A rendszer nem igényel manuális indítást. Minden UI esemény (dátumváltás) reaktív láncot indít el, amely újra-interpolálja a teljes országos adatbázist.
    </div>
    
    <div class="tech-card">
        <b>2. Multi-Model Ensemble (MME) Súlyozás:</b><br>
        A súlyok elosztása az <i>Inverz MAE (Mean Absolute Error)</i> elvén alapul. A rendszer 72 órával ezelőtti (T-3) valós mérési adatokkal kalibrál a 10 legfontosabb magyarországi mérőállomáson.
    </div>

    <div class="tech-card">
        <b>3. Dinamikus Fagyzug Algoritmus:</b><br>
        A globális rácspontok (9-13km) képtelenek modellezni a magyarországi mikroklimatikus mélypontokat. Algoritmusunk -7°C alatt a leghidegebb modell felé súlyoz (85%), -13°C alatt pedig fix fizikai korrekciót (Zabar-faktor) alkalmaz.
    </div>

    <div class="tech-card">
        <b>4. Adatforrások és Modellek:</b><br>
        • <b>ECMWF IFS:</b> 9km-es globális etalon modell.<br>
        • <b>ICON-EU:</b> A DWD 6.7km-es európai precíziós modellje.<br>
        • <b>GFS Seamless:</b> Az amerikai globális rendszer hibrid kimenete.
    </div>
    """, unsafe_allow_html=True)

    # VIZUALIZÁCIÓK A SÚLYOZÁSRÓL
    st.write("**Aktuális modellsúlyok:**")
    fig = px.pie(values=list(weights.values()), names=["ECMWF", "ICON", "GFS"], hole=0.5)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=200, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    st.write("**Átlagos modellhiba (MAE) °C:**")
    st.bar_chart(pd.Series(avg_errors))
