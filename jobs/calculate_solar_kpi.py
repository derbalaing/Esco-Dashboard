import pandas as pd

import sys
import os

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)


from sqlalchemy import text
from config.database import engine

# ======================================
# Lecture des données
# ======================================

query = """
SELECT
    sp.site_id,
    sp.production_date,
    sp.production_kwh,	
    sp.status AS production_status,

    si.panel_power_wc,
    si.panel_quantity,
    si.ipv_efficiency,

    st.target_kwh_kwc_day

FROM solar_productions sp

INNER JOIN solar_installations si
    ON sp.site_id = si.site_id

INNER JOIN solar_targets st
    ON st.site_id = sp.site_id
    AND st.month_number =
        EXTRACT(MONTH FROM sp.production_date)
"""

df = pd.read_sql(query, engine)

print(f"Lignes lues : {len(df)}")

# ======================================
# Calcul puissance installée
# ======================================


df["installed_power_kwc"] = (
    df["panel_power_wc"]
    * df["panel_quantity"]
    / 1000
)



df["ipv_efficiency"] = (
    df["ipv_efficiency"]
    .fillna(100)
)

# ======================================
# Calcul Target Journalier
# ======================================

df["target_kwh"] = (
    df["installed_power_kwc"]
    * df["target_kwh_kwc_day"]
    * (df["ipv_efficiency"] )
)

# ======================================
# Production réelle
# ======================================

df["actual_production_kwh"] = (
    df["production_kwh"]
)

# ======================================
# Performance
# ======================================

df["performance_percent"] = (
    df["actual_production_kwh"]
    / df["target_kwh"]
    * 100
)

df["performance_percent"] = (
    df["performance_percent"]
    .round(2)
)

# ======================================
# Variance
# ======================================

df["variance_kwh"] = (
    df["actual_production_kwh"]
    - df["target_kwh"]
)

df["variance_kwh"] = (
    df["variance_kwh"]
    .round(2)
)

# ======================================
# Status
# ======================================

df["status"] = "NORMAL"

# LostCom

df.loc[
    df["production_status"] == "LOSTCOM",
    "status"
] = "LOSTCOM"

# Production nulle

df.loc[
    df["actual_production_kwh"] == 0,
    "status"
] = "NO_PRODUCTION"

# Faible production

df.loc[
    (
        df["performance_percent"] < 50
    )
    &
    (
        df["status"] == "NORMAL"
    ),
    "status"
] = "LOW_PRODUCTION"

# ======================================
# Colonnes finales
# ======================================

kpi_df = df[
    [
        "site_id",
        "production_date",
        "installed_power_kwc",
        "target_kwh",
        "actual_production_kwh",
        "performance_percent",
        "variance_kwh",
        "status"
    ]
].copy()

kpi_df.rename(
    columns={
        "production_date": "kpi_date"
    },
    inplace=True
)

# ======================================
# Suppression des doublons
# ======================================

kpi_df.drop_duplicates(
    subset=["site_id", "kpi_date"],
    inplace=True
)

# ======================================
# Contrôle
# ======================================

print("\nStatut KPI")

print(
    kpi_df["status"]
    .value_counts()
)

print("\nAperçu")

print(
    kpi_df.head()
)

# ======================================
# Nettoyage table KPI
# ======================================

with engine.begin() as conn:

    conn.execute(
        text(
            """
            TRUNCATE TABLE solar_kpi_daily
            """
        )
    )

# ======================================
# Insertion
# ======================================

kpi_df.to_sql(
    "solar_kpi_daily",
    engine,
    if_exists="append",
    index=False,
    method="multi",
    chunksize=1000
)

print(
    f"\n✅ {len(kpi_df)} KPI calculés"
)