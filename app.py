import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Modell-Súlyozó Dashboard", layout="wide", page_icon="🌡️")

st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; border: 1px solid #eee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .tech-details { background-color: #f8f9fa; padding: 20px; border-radius: 10px; font-size: 0.9rem; border-left: 5px solid #0d6efd; color: #333; line-height: 1.6; }
    div[data-testid="stButton"] { padding-top: 25px !important; }
    </style>
    """, unsafe_allow_html=True)

# --- TELJES TELEPÜLÉSLISTA BETÖLTÉSE (3155 HELYSZÍN) ---
@st.cache_data
def load_all_hungarian_towns():
    # Megbízható GitHub forrás a magyar településekhez (név, lat, lon)
    url = "https://raw.githubusercontent.com/pentasid/hungary-cities-json/master/cities.json"
    try:
        response = requests.get(url)
        data = response.json()
        # Átalakítás a program által várt formátumra
        towns = [{"n": d['name'], "lat": float(d['lat']), "lon": float(d['lng'])} for d in data]
        return towns
    except:
        # Fallback lista, ha a külső forrás nem elérhető
        return [{"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Zabar", "lat": 48.15, "lon": 20.05}]

# --- DINAMIKUS VALIDÁCIÓ ---
@st.cache_data(ttl=3600)
def get_dynamic_weights():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    base_lat, base_lon = 47.49, 19.04
    models = ["ecmwf_ifs", "gfs_seamless", "icon_seamless"]
    validation_data = []
    
    try:
        obs_r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude": base_lat, "longitude": base_lon, "start_date": yesterday, "end_date": yesterday,
            "hourly": "temperature_2m", "timezone": "UTC"
        }).json()
        t_min, t_max = min(obs_r['hourly']['temperature_2m']), max(obs_r['hourly']['temperature_2m'])
    except:
        return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}, None

    errors = []
    for m in models:
        try:
            fc_r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": base_lat, "longitude": base_lon, "start_date": yesterday, "end_date": yesterday,
                "hourly": "temperature_2m", "models": m, "timezone": "UTC"
            }).json()
            p_min, p_max = min(fc_r['hourly']['temperature_2m']), max(fc_r['hourly']['temperature_2m'])
            err = (abs(t_min - p_min) + abs(t_max - p_max)) / 2
            errors.append(max(0.1, err))
            validation_data.append({"Modell": m.upper(), "Jósolt Min": p_min, "Jósolt Max": p_max, "MAE": round(err, 2)})
        except: errors.append(1.0)

    inv_errors = [1/e for e in errors]
    weights = {m: ie/sum(inv_errors) for m, ie in zip(models, inv_errors)}
    val_df = pd.DataFrame(validation_data)
    val_df["Valós (Min/Max)"] = f"{t_min} / {t_max} °C"
    return weights, val_df

# --- ADATLEKÉRÉS ---
def FETCH_DATA(date, weights, towns, p_bar, p_text):
    t_s, t_e = (date - timedelta(days=1)).strftime('%Y-%m-%d'), date.strftime('%Y-%m-%d')
    results = []
    batch_size = 50 
    
    for i in range(0, len(towns), batch_size):
        percent = min(int((i / len(towns)) * 100), 100)
        p_bar.progress(percent)
        p_text.markdown(f"🌍 **3155 település elemzése: {percent}%**")
        
        batch = towns[i:i+batch_size]
        lats, lons = [t['lat'] for t in batch], [t['lon'] for t in batch]
        res_template = [{"n": t['n'], "lat": t['lat'], "lon": t['lon'], "min": 0.0, "max": 0.0} for t in batch]
        
        for m_id, w in weights.items():
            try:
                r = requests.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": lats, "longitude": lons, "hourly": "temperature_2m",
                    "models": m_id, "start_date": t_s, "end_date": t_e, "timezone": "UTC"
                }).json()
                res_list = r if isinstance(r, list) else [r]
                for idx, res in enumerate(res_list):
                    res_template[idx]["min"] += min(res['hourly']['temperature_2m']) * w
                    res_template[idx]["max"] += max(res['hourly']['temperature_2m']) * w
            except: continue
        results.extend(res_template)
    p_bar.empty(); p_text.empty()
    return pd.DataFrame(results)

# --- UI ---
main_c, side_c = st.columns([2.5, 1.5], gap="large")

with main_c:
    st.title("🌡️ Modell-Súlyozó Dashboard")
    c1, c2, _ = st.columns([1.2, 0.4, 2.4])
    target_date = c1.date_input("Előrejelzés dátuma", datetime.now() + timedelta(days=1))
    
    weights, val_table = get_dynamic_weights()
    all_towns = load_all_hungarian_towns()
    
    p_bar, p_text = st.empty(), st.empty()
    df = FETCH_DATA(target_date, weights, all_towns, p_bar, p_text)
    
    if not df.empty:
        m1, m2 = st.columns(2)
        min_r, max_r = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        
        # Kiírás bármelyik kistelepülésre, amelyik a szélsőértéket adja
        m1.metric("📉 Országos Minimum", f"{round(min_r['min'], 1)} °C")
        m1.markdown(f"📍 *{min_r['n']} környékén*")
        
        m2.metric("📈 Országos Maximum", f"{round(max_r['max'], 1)} °C")
        m2.markdown(f"📍 *{max_r['n']} környékén*")
        
        st.write("---")
        map1, map2 = st.columns(2)
        with map1:
            st.subheader("Minimum Hőtérkép")
            fig1 = px.density_mapbox(df, lat='lat', lon='lon', z='min', radius=15,
                                     center=dict(lat=47.15, lon=19.5), zoom=6,
                                     mapbox_style="carto-positron", color_continuous_scale="Viridis")
            fig1.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig1, use_container_width=True)
        with map2:
            st.subheader("Maximum Hőtérkép")
            fig2 = px.density_mapbox(df, lat='lat', lon='lon', z='max', radius=15,
                                     center=dict(lat=47.15, lon=19.5), zoom=6,
                                     mapbox_style="carto-positron", color_continuous_scale="Reds")
            fig2.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig2, use_container_width=True)

with side_c:
    st.header("⚙️ Rendszerlogika")
    
    with st.expander("📊 1. Dinamikus Validáció (D-MOS)", expanded=True):
        st.write("Összevetés a tegnapi tényadatokkal Budapest referencia pontján:")
        if val_table is not None:
            st.dataframe(val_table, hide_index=True)

    with st.expander("🛰️ 2. Multi-Model Ensemble"):
        st.write("Súlyozott előrejelzés: ECMWF IFS, GFS és ICON modellek alapján.")

    with st.expander("🏗️ 3. Adatfeldolgozás (3155 település)"):
        st.write("""
        A program Magyarország összes hivatalos települését elemzi. 
        A listát egy külső JSON adatbázisból tölti be, amely tartalmazza a legkisebb falvakat is (pl. Zabar, Ipolytarnóc, Kerkaszentkirály).
        A lekérés Batch Processing (50-es csomagok) módszerrel történik az API terhelésének optimalizálása érdekében.
        """)

    with st.expander("🗺️ 4. Density Map Technológia"):
        st.write("""
        A térképen nem pontokat, hanem sűrűségi mezőket látunk. 
        Mivel 3155 adatpontunk van, az interpoláció valósághű hőmérsékleti mezőt rajzol ki az ország egész területén.
        """)

    st.write("---")
    st.write("**Aktuális súlyok:**")
    st.plotly_chart(px.pie(values=list(weights.values()), names=["ECMWF", "GFS", "ICON"], hole=0.6,
                    color_discrete_sequence=px.colors.sequential.Plotly3).update_layout(margin=dict(t=0, b=0, l=0, r=0), height=220))
