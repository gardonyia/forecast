import streamlit as st
import requests
import xarray as xr
import numpy as np
import datetime as dt
import tempfile
import cfgrib

st.set_page_config(page_title="HU Országos hőmérsékleti előrejelzés – GFS 0.25°", layout="wide")

# -----------------------------
# IDŐINTERVALLUM
# -----------------------------
now = dt.datetime.utcnow()
tomorrow = now.date() + dt.timedelta(days=1)
day_after = now.date() + dt.timedelta(days=2)

start_time = dt.datetime.combine(tomorrow, dt.time(18, 0))
end_time = dt.datetime.combine(day_after, dt.time(18, 0))

start_str = start_time.strftime("%Y.%m.%d 18:00 UTC")
end_str = end_time.strftime("%Y.%m.%d 18:00 UTC")

# -----------------------------
# GFS FUTÁS
# -----------------------------
current_hour = now.hour
cycle = max([h for h in [0, 6, 12, 18] if h <= current_hour])
cycle_str = f"{cycle:02d}"
date_str = now.strftime("%Y%m%d")

start_cycle = dt.datetime.strptime(date_str + cycle_str, "%Y%m%d%H")

hours = list(range(0, 385, 3))
valid_hours = []

for h in hours:
    t = start_cycle + dt.timedelta(hours=h)
    if start_time <= t <= end_time:
        valid_hours.append(h)

if not valid_hours:
    closest = min(hours, key=lambda h: abs((start_cycle + dt.timedelta(hours=h)) - start_time))
    valid_hours = [closest]

# -----------------------------
# CÍM
# -----------------------------
st.title("HU Országos hőmérsékleti előrejelzés – GFS 0.25°")
st.write(f"**Érvényes időablak:** {start_str} → {end_str}")
st.write(f"**GFS futás:** {date_str} {cycle_str}z")
st.write("**Modell:** NOAA GFS 0.25°, változó: 2 m hőmérséklet")

# -----------------------------
# LETÖLTÉS + ELŐREJELZÉS
# -----------------------------
if st.button("🔍 Előrejelzés kiszámítása"):

    t2m_values = []

    for fh in valid_hours:
        # ÚJ NOAA FILTER API (nincs 403!)
        url = (
            "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?"
            f"file=gfs.t{cycle_str}z.pgrb2.0p25.f{fh:03d}"
            "&var_tmp=on"
            "&lev_2_m_above_ground=on"
            "&subregion=&leftlon=16&rightlon=23&toplat=48.5&bottomlat=45.5"
            f"&dir=%2Fgfs.{date_str}%2F{cycle_str}%2Fatmos"
        )

        try:
            response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name

            ds = xr.open_dataset(
                tmp_path,
                engine="cfgrib",
                backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround", "level": 2}}
            )

            arr = ds["t2m"].values - 273.15  # Kelvin → Celsius
            t2m_values.append(arr)

        except Exception as e:
            st.error(f"GRIB hiba ({fh:03d} óra): {e}")
            continue

    if not t2m_values:
        st.error("Nem sikerült adatot letölteni a NOAA-tól.")
        st.stop()

    merged = np.stack(t2m_values, axis=0)
    tmin = float(np.nanmin(merged))
    tmax = float(np.nanmax(merged))

    st.subheader("📊 Országos előrejelzés eredménye")
    st.success(f"**Országos minimum:** {tmin:.1f} °C")
    st.success(f"**Országos maximum:** {tmax:.1f} °C")

    st.subheader("🌡️ Hőtérkép előnézet")
    st.image(
        "/mnt/data/cc597a8d-a6af-41f1-bfe8-eec954d546c8.png",
        caption="Hőtérkép-animáció előnézete (statikus preview)",
        use_column_width=True
    )
