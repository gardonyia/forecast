import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

# --- OLDAL BEÁLLÍTÁSAI ---
st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide")

# --- SZIGORÍTOTT HATÁRVONAL ÉS VIZUALIZÁCIÓ ---
# Ez a poligon végzi a szűrést, hogy ne kerüljön be külföldi adat (román, szlovák, stb.)
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# Városok a szélsőértékek beazonosításához
CITIES = [
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Győr", "lat": 47.68, "lon": 17.63},
    {"n": "Sopron", "lat": 47.68, "lon": 16.59}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Pécs", "lat": 46.07, "lon": 18.23}, {"n": "Zalaegerszeg", "lat": 46.84, "lon": 16.84},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Békéscsaba", "lat": 46.68, "lon": 21.09},
    {"n": "Salgótarján", "lat": 48.10, "lon": 19.80}, {"n": "Eger", "lat": 47.90, "lon": 20.37},
    {"n": "Záhony", "lat": 48.41, "lon": 22.17}, {"n": "Baja", "lat": 46.18, "lon": 18.95}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists)[1]

MODELS = {"ecmwf_ifs": "ECMWF", "gfs_seamless": "GFS", "icon_seamless": "ICON"}

@st.cache_data(ttl=3600)
def get_weights_v3():
    # Súlyozás (itt most fix, de a korábbi logika alapján számolható)
    return {"ecmwf_ifs": 0.45, "gfs_seamless": 0.30, "icon_seamless": 0.25}

def fetch_data_v3(date, weights):
    t_s = (date - timedelta(days=1)).strftime('%Y-%m-%dT18:00')
    t_e = date.strftime('%Y-%m-%dT18:00')
    
    # Rácsháló generálása - Csak belföldi pontok
    lats = np.arange(45.8, 48.6, 0.2)
    lons = np.arange(16.2, 22.8, 0.3)
    v_lats, v_lons = [], []
    for la in lats:
        for lo in lons:
            if HU_POLY.contains(Point(lo, la)):
                v_lats.append(la)
                v_lons.append(lo)

    results = [{"lat": la, "lon": lo, "min": 0, "max": 0} for la, lo in zip(v_lats, v_lons)]
    
    # API HÍVÁS DARABOLÁSA (Chunking)
