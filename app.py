import streamlit as st
import requests
import xarray as xr
import pandas as pd
import numpy as np
import datetime as dt
import tempfile
import cfgrib
import matplotlib.pyplot as plt

st.set_page_config(
    page_title="HU Országos hőmérsékleti előrejelzés – GFS 0.25°",
    layout="wide"
)

# -----------------------------
# IDŐINTERVALLUM KISZÁMÍTÁSA
# -----------------------------
now = dt.datetime.utcnow()
tomorrow = now.date() + dt.timedelta(days=1)
day_after = now.date() + dt.timedelta(days=2)

start_time = dt.datetime.combine(tomorrow, dt.time(18, 0))
end_time = dt.datetime.combine(day_after, dt.time(18, 0))

start_str = start_time.strftime("%Y.%m.%d 18:00 UTC")
end_str = end_time.strftime("%Y.%m.%d 18:00 UTC")

# -----------------------------
# GFS FUTÁS MEGHATÁROZÁSA
# -----------------------------
current_hour = now.hour
cycle = max([h for h in [0, 6, 12, 18] if h <= current_hour])

cycle_str = f"{cycle:02d}"
date_str = now.strftime("%Y%m%d")

base_url = (
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
    f"gfs.{date_str}/{cycle_str}/atmos/"
)

# -----------------------------
# VALID FORECAST HOURS
# -----------------------------
start_cycle = dt.datetime.strptime(date_str + cycle_str, "%Y%m%d%H")

hours = list(range(0, 385, 3))
valid_hours = []

for h in hours:
    t = start_cycle + dt.timedelta(hours=h)
    if start_time <= t <= end_time:
        valid_hours.append(h)

if not valid_hours:
    # legközelebbi órát választjuk, ha nincs pontos 3 órás lépés
    closest = min(hours, key=lambda h: abs((start_cycle + dt.timedelta(hours=h)) - start_time))
    valid_hours = [closest]

urls = [
    base_url + f"gfs.t{cycle_str}z.pgrb2.0p25.f{h:03d}"
    for h in valid_hours
]

# -----------------------------
# TITLE
# -----------------------------
st.title("HU Országos hőmérsékleti előrejelzés – GFS 0.25°")
st.write(f"**Érvényes időablak:** {start_str} → {end_str}")
st.write(f"**GFS futás:** {date_str} {cycle_str}z")
st.write("**Modell:** NOAA GFS 0.25°, változó: 2 m hőmérséklet")

# -----------------------------
# GOMB: ELŐREJELZÉS KÉSZÍTÉSE
# -----------------------------
if st.button("🔍 Előrejelzés kiszámítása"):

    all_values = []

    for url in urls:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(r.content)
                tmp_path = tmp.name

            ds = xr.open_dataset(
                tmp_path,
                engine="cfgrib",
                backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround", "level": 2}}
            )

            da = ds["t2m"]  # Kelvin → később Celsius
            hu = da.sel(latitude=slice(48.5, 45.5), longitude=slice(16, 23))

            all_values.append(hu.values - 273.15)

        except Exception as e:
            st.error(f"Hiba történt a GRIB beolvasása során:\n{e}")
            continue

    if not all_values:
        st.error("Nincs beolvasható GFS adat.")
        st.stop()

    merged = np.stack(all_values, axis=0)
    tmin = float(np.nanmin(merged))
    tmax = float(np.nanmax(merged))

    st.subheader("📊 Országos előrejelzés eredménye")
    st.success(f"**Országos minimum:** {tmin:.1f} °C")
    st.success(f"**Országos maximum:** {tmax:.1f} °C")

    # -----------------------------
    # STATIKUS PREVIEW HŐTÉRKÉP
    # -----------------------------
    st.subheader("🌡️ Hőtérkép előnézet (statikus)")
    st.image(
        "/mnt/data/cc597a8d-a6af-41f1-bfe8-eec954d546c8.png",
        caption="Hőtérkép-animáció előnézete (statikus preview)",
        use_column_width=True
    )

