import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- KONFIGURÁCIÓ ---
st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide")

# --- GEOMETRIA ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

CITIES = [
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Sopron", "lat": 47.68, "lon": 16.59}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Zalaegerszeg", "lat": 46.84, "lon": 16.84},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Békéscsaba", "lat": 46.68, "lon": 21.09},
    {"n": "Eger", "lat": 47.90, "lon": 20.37}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

@st.cache_data(ttl=3600)
def get_weights_info():
    return {"ECMWF (Európai)": 0.45, "GFS (Amerikai)": 0.30, "ICON (Német)": 0.25}

def FINAL_STABLE_FETCH(date, weights_map):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    lats = np.arange(45.8, 48.6, 0.25)
    lons = np.arange(16.2, 22.8, 0.35)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la)
                v_lons.append(lo)
    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    w_values = {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}
    chunk_size = 15 
    for i in range(0, len(v_lats), chunk_size):
        curr_lats, curr_lons = v_lats[i:i+chunk_size], v_lons[i:i+chunk_size]
        for m_id, weight in w_values.items():
            try:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {"latitude": curr_lats, "longitude": curr_lons, "hourly": "temperature_2m",
                          "models": m_id, "start_hour": t_s, "end_hour": t_e, "timezone": "UTC"}
                r = requests.get(url, params=params).json()
