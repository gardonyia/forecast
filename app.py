import streamlit as st
import requests
import xarray as xr
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import tempfile
import os

st.set_page_config(page_title="HU Hőmérsékleti előrejelzés – GFS 0.25°", layout="wide")

# -------------------------------
# DÁTUMOK
# -------------------------------
now = datetime.utcnow()

# mindig a futtatás napját használjuk
run_date = now.strftime("%Y%m%d")
run_cycle = "12"   # a 12z futás a legstabilabb

# előrejelzési intervallum: holnap 18:00 UTC – holnapután 18:00 UTC
start_time = (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
end_time   = (now + timedelta(days=2)).replace(hour=18, minute=0, second=0, microsecond=0)

start_str = start_time.strftime("%Y.%m.%d 18:00 UTC")
end_str   = end_time.strftime("%Y.%m.%d 18:00 UTC")

# -------------------------------
# FEJLÉC
# -------------------------------
st.title("HU Országos hőmérsékleti előrejelzés – GFS 0.25°°")

st.write(f"**Érvényes időablak:** {start_str} → {end_str}")
st.write(f"**GFS futás:** {run_date} {run_cycle}z")
st.write("**Modell:** NOAA GFS 0.25°, változó: 2 m hőmérséklet\n")

# -------------------------------
# GFS GRIB letöltési függvény
# -------------------------------
def download_gfs_grib(forecast_hour):
    """
    Letölti a GFS 0.25° GRIB2 fájlt (2 m hőmérséklet - TMP, level=2m above ground)
    """
    url = (
        f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
        f"gfs.{run_date}/{run_cycle}/atmos/gfs.t{run_cycle}z.pgrb2.0p25.f{forecast_hour:03d}"
    )

    st.info(f"GRIB letöltése: f{forecast_hour:03d} • {url}")

    response = requests.get(url)
    if response.status_code != 200:
        st.error(f"Hiba: {response.status_code} – nem sikerült letölteni a GRIB-et.")
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".grib2")
    with open(tmp.name, "wb") as f:
        f.write(response.content)

    return tmp.name

# -------------------------------
# ELŐREJELZÉS KISZÁMÍTÁSA
# -------------------------------
if st.button("🔍 Előrejelzés kiszámítása"):
    st.subheader("Hőmérsékleti előrejelzés számítása")

    # az érintett órák meghatározása
    forecast_hours = list(range(24, 60, 3))   # 24–57 óra között 3 órás felbontás

    temps = []
    times = []

    for fh in forecast_hours:
        grib = download_gfs_grib(fh)
        if grib is None:
            continue

        try:
            ds = xr.open_dataset(grib, engine="cfgrib")
            varname = [v for v in ds.data_vars.keys() if "t2m" in v.lower() or "tmp" in v.lower()][0]
            t = ds[varname]

            # Magyarország koordinátái
            t_hu = t.sel(latitude=slice(48.5, 45.5), longitude=slice(16, 23))
            temps.append(float(t_hu.mean()))
            times.append(now + timedelta(hours=fh))

        except Exception as e:
            st.error(f"GRIB olvasási hiba: {e}")

        os.remove(grib)

    if temps:
        df = pd.DataFrame({"Dátum": times, "T2m (°C)": np.array(temps) - 273.15})
        st.line_chart(df.set_index("Dátum"))
        st.success("✔ Előrejelzés elkészült!")
