import streamlit as st
import requests
import xarray as xr
import cfgrib
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import datetime as dt
import os

st.title("🇭🇺 Országos hőmérsékleti előrejelzés – GFS 0.25°")
st.write("Automatikus időablak: **Holnap 18:00 UTC → Holnapután 18:00 UTC**")
st.write("Modell: **NOAA GFS 0.25°**, változó: 2 m hőmérséklet")

# -------------------------------
# MAIN BUTTON
# -------------------------------
if st.button("📡 Előrejelzés kiszámítása"):

    # --------------------------------------
    # TIME WINDOW — always based on runtime
    # --------------------------------------
    utc_now = dt.datetime.utcnow()

    t0 = (utc_now + dt.timedelta(days=1)).replace(
        hour=18, minute=0, second=0, microsecond=0
    )
    t1 = (utc_now + dt.timedelta(days=2)).replace(
        hour=18, minute=0, second=0, microsecond=0
    )

    st.write(f"Időablak: **{t0} → {t1} UTC**")

    # --------------------------------------
    # Determine latest model cycle
    # --------------------------------------
    def latest_cycle():
        now = dt.datetime.utcnow()
        cycles = [0, 6, 12, 18]
        valid = [c for c in cycles if c <= now.hour]
        if valid:
            cyc = valid[-1]
            return now.strftime("%Y%m%d"), f"{cyc:02d}"
        # ha még nincs futás ma, akkor tegnapi 18 UTC
        prev = now - dt.timedelta(days=1)
        return prev.strftime("%Y%m%d"), "18"

    date, cycle = latest_cycle()

    base_url = (
        f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
        f"gfs.{date}/{cycle}/"
    )
    grib_url = base_url + f"gfs.t{cycle}z.pgrb2.0p25.f003"

    st.write("Letöltés:", grib_url)

    # --------------------------------------
    # DOWNLOAD GRIB
    # --------------------------------------
    try:
        r = requests.get(grib_url, timeout=20)
    except Exception as e:
        st.error(f"Hiba a modell letöltése közben: {e}")
        st.stop()

    with open("gfs.grib2", "wb") as f:
        f.write(r.content)

    # --------------------------------------
    # LOAD MODEL
    # --------------------------------------
    try:
        ds = xr.open_dataset("gfs.grib2", engine="cfgrib")
    except Exception as e:
        st.error(f"GRIB beolvasási hiba: {e}")
        st.stop()

    var = [v for v in ds.data_vars if "t" in v.lower() and "2" in v][0]
    da = ds[var]

    # --------------------------------------
    # HUNGARY POLYGON (embedded)
    # --------------------------------------
    hungary_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [16.113886, 46.683610],
                            [16.202298, 46.852386],
                            [16.370505, 46.841327],
                            [16.564808, 47.106674],
                            [16.904696, 47.231877],
                            [16.979667, 47.683771],
                            [17.488873, 47.867466],
                            [17.857133, 48.005656],
                            [18.696513, 47.880954],
                            [18.777024, 47.596167],
                            [19.174365, 47.758429],
                            [19.661365, 47.512153],
                            [20.865771, 48.081768],
                            [21.626473, 48.422264],
                            [22.281444, 48.425780],
                            [22.640820, 48.150127],
                            [22.091312, 47.672439],
                            [21.626413, 47.303681],
                            [21.021952, 46.994239],
                            [20.220192, 46.775486],
                            [19.596044, 46.127469],
                            [18.829838, 45.952221],
                            [18.456062, 45.759481],
                            [17.630066, 45.951692],
                            [16.882515, 46.380632],
                            [16.564808, 46.503181],
                            [16.113886, 46.683610]
                        ]
                    ]
                }
            }
        ]
    }

    hu = gpd.GeoDataFrame.from_features(hungary_geojson).set_crs("EPSG:4326")
    poly = hu.geometry.iloc[0]

    # --------------------------------------
    # MASK GRID FOR HUNGARY
    # --------------------------------------
    lons = da.longitude.values
    lats = da.latitude.values

    points = np.array([[Point(float(lon), float(lat)) for lon in lons] for lat in lats])

    mask = np.array(
        [
            [poly.contains(points[i][j]) for j in range(len(lons))]
            for i in range(len(lats))
        ]
    )

    masked = da.where(mask)

    # Convert K → °C
    masked_c = masked - 273.15

    # --------------------------------------
    # SUBSET TIME RANGE
    # --------------------------------------
    t0_np = np.datetime64(t0)
    t1_np = np.datetime64(t1)

    sub = masked_c.sel(time=slice(t0_np, t1_np))

    # --------------------------------------
    # COMPUTE MIN/MAX
    # --------------------------------------
    tmin = float(sub.min().values)
    tmax = float(sub.max().values)

    # --------------------------------------
    # OUTPUT
    # --------------------------------------
    st.success(f"🇭🇺 Országos minimum hőmérséklet: **{tmin:.1f} °C**")
    st.success(f"🇭🇺 Országos maximum hőmérséklet: **{tmax:.1f} °C**")

    st.write("Forrás: NOAA GFS 0.25° modell")
    st.write("A számítás minden futáskor az aktuális időponthoz igazodik.")

