import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- UI/UX KONFIGURÁCIÓ ---
st.set_page_config(page_title="Met-Ensemble Pro", layout="wide")

# Egyedi CSS a modern megjelenéshez
st.markdown("""
    <style>
    .metric-container { background-color: #f0f2f6; padding: 25px; border-radius: 15px; border: 1px solid #dfe3e8; }
    .main-title { font-size: 2.2rem; color: #1e293b; font-weight: 800; margin-bottom: 0.5rem; }
    .method-card { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 1rem; }
    .step-header { color: #0f172a; font-weight: 700; border-bottom: 2px solid #3b82f6; padding-bottom: 5px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- KONSTANSOK ---
MODELS = {"ecmwf_ifs": "ECMWF", "icon_eu": "ICON-EU", "gfs_seamless": "GFS"}
TOP_10_CITIES = [
    {"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Szeged", "lat": 46.25, "lon": 20.14}, {"n": "Miskolc", "lat": 48.10, "lon": 20.78},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"n": "Kecskemét", "lat": 46.90, "lon": 19.69},
    {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41}, {"n": "Szombathely", "lat": 47.23, "lon": 16.62}
]

# --- ADATFELDOLGOZÓ FÜGGVÉNYEK ---
@st.cache_data(ttl=3600)
def calibrate_weights():
    # T-2 napos validáció a megbízható mérési adatokért
    val_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    matrix, errors = [], {m: [] for m in MODELS}
    
    for city in TOP_10_CITIES:
        try:
            # Valóság (Archive)
            obs = requests.get(f"https://archive-api.open-meteo.com/v1/archive?latitude={city['lat']}&longitude={city['lon']}&start_date={val_date}&end_date={val_date}&hourly=temperature_2m").json()
            t_real_min, t_real_max = min(obs['hourly']['temperature_2m']), max(obs['hourly']['temperature_2m'])
            
            row = {"Város": city['n'], "Mért (Min/Max)": f"{t_real_min} / {t_real_max} °C"}
            for m in MODELS:
                fc = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={city['lat']}&longitude={city['lon']}&start_date={val_date}&end_date={val_date}&hourly=temperature_2m&models={m}").json()
                p_min, p_max = min(fc['hourly']['temperature_2m']), max(fc['hourly']['temperature_2m'])
                errors[m].append((abs(t_real_min - p_min) + abs(t_real_max - p_max)) / 2)
                row[f"{MODELS[m]} jóslat"] = f"{p_min} / {p_max}"
            matrix.append(row)
        except: continue
        
    avg_errs = {m: np.mean(errors[m]) for m in MODELS}
    inv = [1/avg_errs[m] for m in MODELS]
    weights = {m: inv[i]/sum(inv) for i, m in enumerate(MODELS)}
    return weights, pd.DataFrame(matrix), avg_errs

def run_national_forecast(target_date, weights):
    # Városlista betöltése (3155 település)
    towns = requests.get("https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json").json()
    results = []
    t_s, t_e = (target_date - timedelta(days=1)).strftime('%Y-%m-%d'), target_date.strftime('%Y-%m-%d')
    
    p_bar = st.progress(0, "Települések elemzése...")
    for i in range(0, len(towns), 200):
        batch = towns[i:i+200]
        lats, lons = [float(t['lat']) for t in batch], [float(t['lng']) for t in batch]
        
        batch_df = pd.DataFrame([{"n": t['name'], "min": 0.0, "max": 0.0} for t in batch])
        model_mins = []
        
        for m, w in weights.items():
            r = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str,lats))}&longitude={','.join(map(str,lons))}&hourly=temperature_2m&models={m}&start_date={t_s}&end_date={t_e}&timezone=UTC").json()
            res_list = r if isinstance(r, list) else [r]
            
            m_batch_mins = []
            for idx, res in enumerate(res_list):
                temps = res['hourly']['temperature_2m']
                batch_df.at[idx, "min"] += min(temps) * w
                batch_df.at[idx, "max"] += max(temps) * w
                m_batch_mins.append(min(temps))
            model_mins.append(m_batch_mins)

        # Fagyzug korrekció
        for idx in range(len(batch_df)):
            abs_min = min([m[idx] for m in model_mins])
            if abs_min < -8: # Extrém hideg esetén a leghidegebb modell súlya nő
                batch_df.at[idx, "min"] = (batch_df.at[idx, "min"] * 0.2) + (abs_min * 0.8)
                if abs_min < -12: batch_df.at[idx, "min"] -= 3.0
        
        results.append(batch_df)
        p_bar.progress(min((i+200)/len(towns), 1.0))
    
    p_bar.empty()
    return pd.concat(results)

# --- DASHBOARD UI ---
st.markdown('<div class="main-title">🌡️ Met-Ensemble Pro Dashboard</div>', unsafe_allow_html=True)
st.write("Dinamikus modellsúlyozáson alapuló országos meteorológiai előrejelző rendszer.")

col_main, col_tech = st.columns([1.8, 1.2], gap="large")

with col_main:
    # UX: Jövőbeli dátum korlátozás
    min_date = datetime.now().date() + timedelta(days=1)
    max_date = datetime.now().date() + timedelta(days=14)
    
    st.subheader("📅 Időpont kiválasztása")
    selected_date = st.date_input("Válasszon egy jövőbeli napot:", 
                                  value=min_date, 
                                  min_value=min_date, 
                                  max_value=max_date)
    
    st.info(f"Az elemzés a(z) **{selected_date}** napra fog lefutni 3155 magyarországi település figyelembevételével.")
    
    weights, val_df, errors = calibrate_weights()
    
    if st.button("🚀 Országos Előrejelzés Generálása", use_container_width=True):
        final_df = run_national_forecast(selected_date, weights)
        
        st.write("---")
        res_min = final_df.loc[final_df['min'].idxmin()]
        res_max = final_df.loc[final_df['max'].idxmax()]
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div class="metric-container">
                <p style="color: #3b82f6; font-weight: bold; margin:0;">📉 ORSZÁGOS MINIMUM</p>
                <h1 style="margin:0;">{round(res_min['min'], 1)} °C</h1>
                <p style="color: #64748b; margin:0;">📍 {res_min['n']} és környéke</p>
            </div>
            """, unsafe_allow_html=True)
            
        with c2:
            st.markdown(f"""
            <div class="metric-container">
                <p style="color: #ef4444; font-weight: bold; margin:0;">📈 ORSZÁGOS MAXIMUM</p>
                <h1 style="margin:0;">{round(res_max['max'], 1)} °C</h1>
                <p style="color: #64748b; margin:0;">📍 {res_max['n']} és környéke</p>
            </div>
            """, unsafe_allow_html=True)

    st.write("---")
    st.subheader("📊 Tegnapi Validációs Adatok")
    st.dataframe(val_df, use_container_width=True, hide_index=True)

with col_tech:
    st.subheader("📘 Kibővített Technikai Leírás")
    
    with st.container():
        st.markdown("""
        <div class="method-card">
            <div class="step-header">1. Dinamikus Súlyozás (D-MOS)</div>
            A rendszer nem statikus súlyokat használ. Minden futás előtt lekéri a 10 legnépesebb magyar város 
            <b>mért tényadatait</b> és összeveti azokat a modellek korábbi jóslataival. 
            A súlyozás az <i>Inverz Átlagos Abszolút Hiba (I-MAE)</i> módszerével történik.
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="method-card">
            <div class="step-header">2. Ensemble Összetétel</div>
            • <b>ECMWF IFS (45-55%):</b> Globális piacvezető modell (9 km rács).<br>
            • <b>ICON-EU (30-40%):</b> Európai precíziós modell (6.7 km rács).<br>
            • <b>GFS (10-20%):</b> Amerikai globális modell (13 km rács).
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="method-card">
            <div class="step-header">3. Fagyzug és Kisugárzási Algoritmus</div>
            Mivel a globális modellek nem látják a magyarországi mikroklimatikus völgyeket, 
            a rendszer -8°C alatt aktivál egy <b>nem-lineáris korrekciós faktort</b>. 
            Ez a faktor a leghidegebb modell eredményét preferálja, szimulálva a derült, szélcsendes éjszakák 
            extrém lehűlését (pl. Zabar, Mohos-töbör).
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="method-card">
            <div class="step-header">4. UI/UX Irányelvek</div>
            • <b>Dátum-validáció:</b> Csak jövőbeli (T+1 és T+14 közötti) adatok kérhetők le.<br>
            • <b>Batch Processing:</b> A 3155 település elemzése 200-as csomagokban történik az API stabilitásáért.<br>
            • <b>Lokáció-azonosítás:</b> Az algoritmus nem csak értéket, hanem pontos településnevet is rendel a szélsőértékekhez.
        </div>
        """, unsafe_allow_html=True)

    st.write("**Aktuális modell-pontosság (MAE):**")
    st.bar_chart(pd.Series(errors))
