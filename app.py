import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. UI/UX KONFIGURÁCIÓ (85%-OS KOMPAKT NÉZET) ---
st.set_page_config(page_title="Met-Ensemble Pro v5.1", layout="wide")

st.markdown("""
    <style>
    /* Oldalszélesség és alap betűméret csökkentése a sűrűbb tartalomért */
    .main .block-container { max-width: 92%; padding-top: 1rem; padding-bottom: 1rem; }
    html { font-size: 13px; } 
    
    .result-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border-top: 4px solid #2563eb; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); text-align: center; margin-bottom: 10px; }
    .tech-card { background-color: #f1f5f9; padding: 12px; border-radius: 8px; border-left: 5px solid #334155; margin-bottom: 8px; line-height: 1.4; }
    .status-badge { background-color: #e2e8f0; color: #475569; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; font-weight: bold; }
    .stTable { font-size: 0.85rem !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ADATBÁZIS ÉS FALLBACK KEZELÉS ---
@st.cache_data
def load_hungarian_towns():
    try:
        # Próbáljuk letölteni a 3155 település adatait
        r = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json", timeout=8)
        return r.json()
    except:
        # Vészhelyzeti fallback lista, ha a távoli adatbázis nem elérhető
        return [
            {"name": "Budapest", "lat": 47.49, "lng": 19.04},
            {"name": "Zabar", "lat": 48.15, "lng": 20.25},
            {"name": "Debrecen", "lat": 47.53, "lng": 21.62},
            {"name": "Szeged", "lat": 46.25, "lng": 20.14}
        ]

# --- 3. DINAMIKUS KALIBRÁCIÓ (T-4 NAP A HITELLES MÉRÉSEKÉRT) ---
@st.cache_data(ttl=3600)
def get_system_calibration():
    # T-4 nap: Az API itt már biztosan a valós állomási méréseket adja vissza, nem modell-becslést
    val_date = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d')
    cities = [
        {"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
        {"n": "Szeged", "lat": 46.25, "lon": 20.14}, {"n": "Miskolc", "lat": 48.10, "lon": 20.78},
        {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Győr", "lat": 47.68, "lon": 17.63}
    ]
    models = {"ecmwf_ifs": "ECMWF", "icon_eu": "ICON", "gfs_seamless": "GFS"}
    
    m_rows, err_map = [], {m: [] for m in models}
    
    for c in cities:
        try:
            # Archív mérések
            obs = requests.get(f"https://archive-api.open-meteo.com/v1/archive?latitude={c['lat']}&longitude={c['lon']}&start_date={val_date}&end_date={val_date}&hourly=temperature_2m", timeout=5).json()
            t_real_min = min(obs['hourly']['temperature_2m'])
            t_real_max = max(obs['hourly']['temperature_2m'])
            
            row = {"Város": c['n'], "Mért (Min/Max)": f"{t_real_min} / {t_real_max} °C"}
            for m_id, m_name in models.items():
                fc = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={c['lat']}&longitude={c['lon']}&start_date={val_date}&end_date={val_date}&hourly=temperature_2m&models={m_id}", timeout=5).json()
                p_min, p_max = min(fc['hourly']['temperature_2m']), max(fc['hourly']['temperature_2m'])
                
                # Hiba számítása (MAE)
                err = (abs(t_real_min - p_min) + abs(t_real_max - p_max)) / 2
                err_map[m_id].append(max(0.4, err)) # Mesterséges zaj a 0-val osztás ellen
                row[f"{m_name} jósolt"] = f"{p_min} / {p_max}"
            m_rows.append(row)
        except: continue
        
    avg_mae = {m: np.mean(err_map[m]) for m in models}
    inv = [1/avg_mae[m] for m in models]
    weights = {m: inv[i]/sum(inv) for i, m in enumerate(models)}
    return weights, pd.DataFrame(m_rows), avg_mae

# --- 4. REAKTÍV ELŐREJELZŐ MOTOR ---
def run_national_forecast(target_date, weights):
    towns = load_hungarian_towns()
    t_s = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    t_e = target_date.strftime('%Y-%m-%d')
    
    final_results = []
    
    # Batch feldolgozás az API stabilitásáért
    for i in range(0, len(towns), 400):
        batch = towns[i:i+400]
        lats, lons = [float(t.get('lat', t.get('latitude', 47))) for t in batch], [float(t.get('lng', t.get('longitude', 19))) for t in batch]
        
        batch_df = pd.DataFrame([{"n": t.get('name', 'Ismeretlen'), "min": 0.0, "max": 0.0} for t in batch])
        m_mins_data = []

        for m_id, w in weights.items():
            url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m_id}&start_date={t_s}&end_date={t_e}&timezone=UTC"
            resp = requests.get(url).json()
            res_list = resp if isinstance(resp, list) else [resp]
            
            m_batch_mins = []
            for idx, r in enumerate(res_list):
                temps = r['hourly']['temperature_2m']
                batch_df.at[idx, "min"] += min(temps) * w
                batch_df.at[idx, "max"] += max(temps) * w
                m_batch_mins.append(min(temps))
            m_mins_data.append(m_batch_mins)

        # --- FAGYZUG MODUL LOGIKA ---
        for idx in range(len(batch_df)):
            abs_min = min([m[idx] for m in m_mins_data])
            # -7 fok alatt a leghidegebb modell dominanciája (Inverziós hűtés)
            if abs_min < -7:
                batch_df.at[idx, "min"] = (batch_df.at[idx, "min"] * 0.15) + (abs_min * 0.85)
            # -13 fok alatt extra kisugárzási korrekció (Völgy-faktor)
            if abs_min < -13:
                batch_df.at[idx, "min"] -= 4.2
        
        final_results.append(batch_df)
        
    return pd.concat(final_results)

# --- 5. DASHBOARD ÖSSZEÁLLÍTÁSA ---
st.title("🌡️ Met-Ensemble Pro v5.1")

# Adatok előkészítése (Globális változók a NameError ellen)
try:
    weights, val_df, mae_stats = get_system_calibration()
except:
    weights = {"ecmwf_ifs": 0.4, "icon_eu": 0.4, "gfs_seamless": 0.2}
    val_df = pd.DataFrame()
    mae_stats = {"ecmwf_ifs": 1.0, "icon_eu": 1.0, "gfs_seamless": 1.0}

col_main, col_tech = st.columns([1.7, 1.3], gap="medium")

with col_main:
    st.subheader("📅 Aktív Országos Előrejelzés")
    target_date = st.date_input("Válasszon egy jövőbeli napot:", 
                                value=datetime.now().date() + timedelta(days=1),
                                min_value=datetime.now().date() + timedelta(days=1))
    
    with st.spinner("3155 település elemzése folyamatban..."):
        results = run_national_forecast(target_date, weights)
        res_min = results.loc[results['min'].idxmin()]
        res_max = results.loc[results['max'].idxmax()]

    # Kiemelt eredmények kártyákon
    st.write("---")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown(f"""<div class="result-card" style="border-top-color: #2563eb; background-color: #f0f7ff;">
            <span class="status-badge">Minimum</span>
            <h1 style="color:#1e40af; margin:0;">{round(res_min['min'], 1)} °C</h1>
            <p style="font-weight: bold; margin:0;">📍 {res_min['n']}</p>
        </div>""", unsafe_allow_html=True)
    with r2:
        st.markdown(f"""<div class="result-card" style="border-top-color: #dc2626; background-color: #fff1f2;">
            <span class="status-badge">Maximum</span>
            <h1 style="color:#991b1b; margin:0;">{round(res_max['max'], 1)} °C</h1>
            <p style="font-weight: bold; margin:0;">📍 {res_max['n']}</p>
        </div>""", unsafe_allow_html=True)

    st.write("---")
    st.subheader("📊 Validációs Mátrix (T-4 nap mérései)")
    st.table(val_df)

with col_tech:
    st.subheader("📘 Részletes Technikai Dokumentáció")
    
    st.markdown("""
    <div class="tech-card">
        <b>1. Dinamikus Súlyozás (D-MOS):</b><br>
        A rendszer 96 órával ezelőtti (T-4) tényadatok alapján kalibrál. Ez elengedhetetlen, mert az API-szolgáltatók 72 órán belül gyakran a modelladatokat tüntetik fel "mérésként". A T-4 nap már hitelesített állomási adatokat tartalmaz.
    </div>
    
    <div class="tech-card">
        <b>2. Fagyzug és Kisugárzási Modul:</b><br>
        A globális modellek rácsfelbontása (9-13km) nem látja a magyarországi mikroklimatikus csapdákat. <br>
        • <b>Küszöb:</b> -7°C alatt a rendszer 85%-ban a leghidegebb modell kimenetét preferálja.<br>
        • <b>Zabar-faktor:</b> -13°C-os modellérték alatt egy fix -4.2°C-os degressziót alkalmazunk, szimulálva az extrém völgyi kisugárzást.
    </div>
    
    <div class="tech-card">
        <b>3. Batch Feldolgozási Logika:</b><br>
        A 3155 település elemzése nem egyenként, hanem 400-as csoportokban történik. Ez optimalizálja az API hívások számát és drasztikusan csökkenti a futási időt.
    </div>

    <div class="tech-card">
        <b>4. Alkalmazott Modell-Ensemble:</b><br>
        • <b>ECMWF IFS:</b> Globális etalon (nagyfelbontású).<br>
        • <b>ICON-EU:</b> Európai precíziós modell (DWD).<br>
        • <b>GFS Seamless:</b> Amerikai globális korrekciós modell.
    </div>
    """, unsafe_allow_html=True)

    # Vizuális statisztika
    st.write("**Aktuális modellsúlyok:**")
    fig_pie = px.pie(values=list(weights.values()), names=["ECMWF", "ICON", "GFS"], hole=0.5)
    fig_pie.update_layout(height=200, margin=dict(l=0,r=0,b=0,t=0), showlegend=False)
    st.plotly_chart(fig_pie, use_container_width=True)

    st.write("**Modellek átlagos hibája (MAE) °C:**")
    st.bar_chart(pd.Series(mae_stats))
