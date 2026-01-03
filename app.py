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

# VÁROSLISTA - Érd és a nagyobb települések
CITIES = [
    {"n": "Érd", "lat": 47.38, "lon": 18.91}, # Kiemelve az elejére
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
    {"n": "Keszthely", "
