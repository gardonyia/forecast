import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon

st.set_page_config(page_title="Magyarországi Modell-Súlyozó", layout="wide", page_icon="🌡️")

# --- PONTOS ORSZÁGHATÁR ÉS HELYSZÍN ADATBÁZIS ---
HU_COORDS = [
    (16.1, 46.6), (16.2, 47.1), (16.5, 47.5), (17.1, 48.0), (18.1, 48.1), 
    (18.8, 48.1), (19.2, 48.3), (19.8, 48.6), (20.9, 48.6), (22.0, 48.6), 
    (22.8, 48.4), (22.9, 48.0), (22.5, 47.4), (21.6, 46.7), (21.3, 46.2), 
    (20.5, 46.1), (19.4, 46.1), (18.8, 45.8), (17.5, 45.8), (16.6, 46.3), (16.1, 46.5)
]
HU_POLY = Polygon(HU_COORDS)
HU_LINE_LATS = [c[1] for c in HU_COORDS] + [HU_COORDS[0][1]]
HU_LINE_LONS = [c[0] for c in HU_COORDS] + [HU_COORDS[0][0]]

# Városok a koordináták azonosításához
CITIES = [
    {"name": "Szombathely", "lat": 47.23, "lon": 16.62}, {"name": "Győr", "lat": 47.68, "lon": 17.63},
    {"name": "Sopron", "lat": 47.68, "lon": 16.59}, {"name": "Budapest", "lat": 47.49, "lon": 19.04},
    {"name": "Miskolc", "lat": 48.10, "lon": 20.78}, {"name": "Debrecen", "lat": 47.53, "lon": 21.62},
    {"name": "Nyíregyháza", "lat": 47.95, "lon": 21.71}, {"name": "Szeged", "lat": 46.25, "lon": 20.14},
    {"name": "Pécs", "lat": 46.07, "lon": 18.23}, {"name": "Nagykanizsa", "lat": 46.45, "lon": 17.00},
    {"name": "Siófok", "lat": 46.90, "lon": 18.05}, {"name": "Zalaegerszeg", "lat": 46.84, "lon": 16.84},
    {"name": "Kecskemét", "lat": 46.90, "lon": 19.69}, {"name": "Békéscsaba", "lat": 46.68, "lon": 21.09},
    {"name": "Salgótarján", "lat": 48.10, "lon": 19.80}, {"name": "Eger", "lat": 47.90, "lon": 20.37},
    {"name": "Szolnok", "lat": 47.17, "lon": 20.18}, {"name": "Tatabánya", "lat": 47.56, "lon": 18.41},
    {"name": "Szekszárd", "lat": 46.35, "lon": 18.70}, {"name": "Veszprém", "lat": 47.09, "lon
