import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide", page_icon="🌡️")

# --- GEOMETRIA ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# VÁROSLISTA - Érddel az élen
CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91},
    {"n": "Budapest", "lat": 47.49, "lon": 19.04}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Szeged", "lat": 46.25, "lon": 20.14}, {"n": "Miskolc", "lat": 48.10, "lon": 20.78},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"n": "Kecskemét", "lat": 46.90, "lon": 19.69},
    {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41}, {"n": "Szombathely", "lat": 47.23, "lon": 16.62},
    {"n": "Szolnok", "lat": 47.17, "lon": 20.18}, {"n": "Tatabánya", "lat": 47.58, "lon": 18.40},
    {"n": "Sopron", "lat": 47.68, "lon": 16.59}, {"n": "Kaposvár", "lat": 46.35, "lon": 17.78},
    {"n": "Veszprém", "lat": 47.09, "lon": 17.91}, {"n": "Békéscsaba", "lat": 46.68, "lon": 21.09},
    {"n": "Zalaegerszeg", "lat": 46.84, "lon": 16.84}, {"n": "Eger", "lat": 47.90, "lon": 20.37},
    {"n": "Nagykanizsa", "lat": 46.45, "lon": 16.99}, {"n": "Dunakeszi", "lat": 47.63, "lon": 19.13},
    {"n": "Hódmezővásárhely", "lat": 46.41, "lon": 20.32}, {"n": "Salgótarján", "lat": 48.10, "lon": 19.80},
    {"n": "Cegléd", "lat": 47.17, "lon": 19.79}, {"n": "Baja", "lat": 46.18, "lon": 18.95},
    {"n": "Vác", "lat": 47.77, "lon": 19.12}, {"n": "Gödöllő", "lat": 47.59, "lon": 19.35},
    {"n": "Szekszárd", "lat": 46.35, "lon": 18.70}, {"n": "Szigetszentmiklós", "lat": 47.34, "lon": 19.04},
    {"n": "Gyöngyös", "lat": 47.78, "lon": 19.92}, {"n": "Mosonmagyaróvár", "lat": 47.87, "lon": 17.26},
    {"n": "Pápa", "lat": 47.33, "lon": 17.46}, {"n": "Gyula", "lat": 46.64, "lon": 21.28},
    {"n": "Hajdúböszörmény", "lat": 47.67, "lon": 21.50}, {"n": "Esztergom", "lat": 47.79, "lon": 18.74},
    {"n": "Kiskunfélegyháza", "lat": 46.71, "lon": 19.85}, {"n": "Jászberény", "lat": 47.50, "lon": 19.91},
    {"n": "Orosháza", "lat": 46.56, "lon": 20.66}, {"n": "Kazincbarcika", "lat": 48.25, "lon": 20.62},
    {"n": "Szentes", "lat": 46.65, "lon": 20.25}, {"n": "Kiskunhalas", "lat": 46.43, "lon": 19.48},
    {"n": "Dunaújváros", "lat": 46.96, "lon": 18.93}, {"n": "Siófok", "lat": 46.90, "lon": 18.05},
    {"n": "Paks", "lat": 46.62, "lon": 18.85}, {"n": "Hatvan", "lat": 47.66, "lon": 19.68},
    {"n": "Keszthely", "lat": 46.76, "lon": 17.24}, {"n": "Balassagyarmat", "lat": 48.07, "lon": 19.29},
    {"n": "Szerencs", "lat": 48.16, "lon": 21.20}, {"n": "Sátoraljaújhely", "lat": 48.39, "lon": 21.65},
    {"n": "Mezőtúr", "lat": 47.00, "lon": 20.61}, {"n": "Csongrád", "lat": 46.71, "lon": 20.14},
    {"n": "Kalocsa", "lat": 46.52, "lon": 18.97}, {"n": "Berettyóújfalu", "lat": 47.22, "lon": 21.54},
    {"n": "Szarvas", "lat": 46.86, "lon": 20.55}, {"n": "Dombóvár", "lat": 46.37, "lon": 18.13},
    {"n": "Szentendre", "lat": 47.66, "lon": 19.07}, {"n": "Tata", "lat": 47.64, "lon": 18.31},
    {"n": "Karcag", "lat": 47.31, "lon": 20.92}, {"n": "Mohács", "lat": 46.00, "lon": 18.68},
    {"n": "Bátaszék", "lat": 46.18, "lon": 18.72}, {"n": "Záhony", "lat": 48.41, "lon": 22.17},
    {"n": "Budaörs", "lat": 47.46, "lon": 18.95}, {"n": "Szentgotthárd", "lat": 46.95, "lon": 16.27},
    {"n": "Mezőkövesd", "lat": 47.81, "lon": 20.57}, {"n": "Tiszaújváros", "lat": 47.92, "lon": 21.05}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

# --- ADATGYŰJTÉS ---
def FETCH_FINAL_DATA(date):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    # Sűrű rácsháló a precíz méréshez
    lats = np.arange(45.8, 48.6, 0.15) 
    lons = np.arange(16.2, 22.8, 0.18)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la); v_lons.append(lo)

    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    weights = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    
    chunk_size = 10 # Kisebb chunkok a stabilitásért
    for i in range(0, len(v_lats), chunk_size):
        c_lats, c_lons = v_lats[i:i+chunk_size], v_lons[i:i+chunk_size]
        for m_id, w in weights.items():
            try:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": c_lats, "longitude": c_lons, "hourly": "temperature_2m",
                    "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"
                }
                r = requests.get(url, params=params).json()
                pts = r if isinstance(r, list) else [r]
                for j, p in enumerate(pts):
                    if 'hourly' in p:
                        t = p['hourly']['temperature_2m']
                        results[i+j]["min"] += min(t) * w
                        results[i+j]["max"] += max(t) * w
            except Exception as e:
                continue
    return pd.DataFrame(results)

# --- FELÜLET ---
st.title("🌡️ Súlyozott Magyarországi Előrejelző")

with st.expander("ℹ️ Hogyan működik a program? - Módszertan", expanded=True):
    tab1, tab2 = st.tabs(["💡 Közérthető összefoglaló", "⚙️ Technikai háttér"])
    
    with tab1:
        st.write("""
        **Pontosság és hitelesség:**
        Ez az alkalmazás három nagy nemzetközi időjárási modell (Európa, USA, Németország) adatait összefűzve ad megbízhatóbb becslést.
        
        **Lokális mérés:**
        A sűrű rácsháló révén a völgyek és dombságok (fagyzugok) hőmérsékleti különbségeit is látjuk. A szélsőértékeknél a legközelebbi 5000 fő feletti várost (pl. Érd) jelezzük.
        
        **Éghajlati nap:**
        A mérés este 19:00-tól (18:00 UTC) következő este 19:00-ig tart a folytonosság érdekében.
        """)
        
    with tab2:
        st.write("""
        **Szakmai specifikáció:**
        * **Időablak:** Climatological Day ($D_{-1}$ 18:00 UTC - $D_{0}$ 18:00 UTC).
        * **Felbontás:** $0.15^{\circ} \times 0.18^{\circ}$-os rácsfelbontás a mikroklimatikus hatások leképezésére.
        * **Súlyozás:** ECMWF (45%), GFS (30%), ICON (25%).
        """)
        w_df = pd.DataFrame({"Modell": ["ECMWF", "GFS", "ICON"], "Súly": [45, 30, 25]})
        st.plotly_chart(px.pie(w_df, values='Súly', names='Modell', hole=0.4, height=180), use_container_width=True)

st.divider()

if st.sidebar.button("Hard Reset (Adatok frissítése)"):
    st.cache_data.clear()
    st.rerun()

target_date = st.sidebar.date_input("Dátum", datetime.now() + timedelta(days=1))

with st.spinner('Adatok elemzése a sűrű rácshálón (30 mp)...'):
    df = FETCH_FINAL_DATA(target_date)
    if not df.empty:
        min_row, max_row = df.loc[df['min'].idxmin()], df.loc[df['max'].idxmax()]
        min_city, max_city = find_nearest_city(min_row['lat'], min_row['lon']), find_nearest_city(max_row['lat'], max_row['lon'])

        c1, c2 = st.columns(2)
        c1.metric("Országos MIN", f"{round(min_row['min'], 1)} °C", f"({min_city} környéke)")
        c2.metric("Országos MAX", f"{round(max_row['max'], 1)} °C", f"({max_city} környéke)")
        
        m1, m2 = st.columns(2)
        def draw_map(data, col, colors, title):
            fig = px.scatter_mapbox(data, lat="lat", lon="lon", color=col, color_continuous_scale=colors, 
                                    zoom=6.1, center={"lat": 47.15, "lon": 19.5}, mapbox_style="carto-positron")
            fig.add_trace(go.Scattermapbox(lat=HU_LINE_LATS, lon=HU_LINE_LONS, mode='lines', 
                                           line=dict(width=3, color='black'), showlegend=False))
            fig.update_traces(marker=dict(size=12, opacity=0.8))
            fig.update_layout(title=title, margin={"r":0,"t":40,"l":0,"b":0})
            return fig

        m1.plotly_chart(draw_map(df, "min", "Viridis", "Minimumok"), use_container_width=True)
        m2.plotly_chart(draw_map(df, "max", "Reds", "Maximumok"), use_container_width=True)
