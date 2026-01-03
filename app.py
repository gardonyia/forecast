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

# CSS a letisztult kinézethez
st.markdown("""
    <style>
    .main { background-color: #f9f9f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

# --- GEOMETRIA ---
HU_COORDS = [
    (16.11, 46.60), (16.20, 46.95), (16.55, 47.35), (17.05, 47.95), (17.50, 48.05),
    (18.50, 48.10), (19.05, 48.30), (19.80, 48.60), (20.90, 48.55), (22.15, 48.40),
    (22.85, 48.35), (22.95, 47.90), (22.60, 47.45), (21.75, 46.85), (21.40, 46.25),
    (20.50, 46.10), (19.50, 46.05), (18.70, 45.85), (17.50, 45.85), (16.50, 46.25), (16.11, 46.60)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS, HU_LINE_LONS = zip(*[(c[1], c[0]) for c in HU_COORDS])

# VÁROSLISTA (Érddel az élen)
CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91}, {"n": "Budapest", "lat": 47.49, "lon": 19.04},
    {"n": "Debrecen", "lat": 47.53, "lon": 21.62}, {"n": "Szeged", "lat": 46.25, "lon": 20.14},
    {"n": "Miskolc", "lat": 48.10, "lon": 20.78}, {"n": "Pécs", "lat": 46.07, "lon": 18.23},
    {"n": "Győr", "lat": 47.68, "lon": 17.63}, {"n": "Nyíregyháza", "lat": 47.95, "lon": 21.71},
    {"n": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"n": "Székesfehérvár", "lat": 47.18, "lon": 18.41},
    {"n": "Szombathely", "lat": 47.23, "lon": 16.62}, {"n": "Szolnok", "lat": 47.17, "lon": 20.18},
    {"n": "Tatabánya", "lat": 47.58, "lon": 18.40}, {"n": "Sopron", "lat": 47.68, "lon": 16.59},
    {"n": "Veszprém", "lat": 47.09, "lon": 17.91}, {"n": "Eger", "lat": 47.90, "lon": 20.37}
]

def find_nearest_city(lat, lon):
    dists = [((c["lat"] - lat)**2 + (c["lon"] - lon)**2, c["n"]) for c in CITIES]
    return min(dists
