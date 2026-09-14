import pandas as pd

import sys
import os

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)


from config.database import engine

# ======================================
# 1. Lecture du fichier Excel
# ======================================

solar_df = pd.read_excel("data/Solar_batch2026.xlsx")

print(f"Nombre de lignes Solar : {len(solar_df)}")

# ======================================
# 2. Récupération des sites
# ======================================

sites_df = pd.read_sql(
    """
    SELECT
        site_id,
        code_site
    FROM sites
    """,
    engine
)

# ======================================
# 3. Correspondance Code site -> site_id
# ======================================

solar_df = solar_df.merge(
    sites_df,
    left_on="Code site",
    right_on="code_site",
    how="left"
)

# ======================================
# 4. Vérification des sites manquants
# ======================================

missing = solar_df[solar_df["site_id"].isna()]

if not missing.empty:
    print("\nSites non trouvés :")
    print(missing["Code site"].unique())

    raise Exception(
        f"{len(missing)} sites inexistants dans la table sites"
    )

# ======================================
# 5. Renommage colonnes
# ======================================

solar_df = solar_df.rename(
    columns={
        "Types Panneaux solaires installés": "panel_type",
        "Puissance PV en Wc": "panel_power_wc",
        "Nbr PV installés": "panel_quantity",
        "Puissance totale installée (W)": "total_installed_power_wc",
        "Number of solar chargers installed": "solar_chargers_count",
        "Number of slots": "charger_slots",
        "Année Installation": "installation_date",
        "Etat Panneaux solaire installés": "panel_condition",
        "Efficacité de IPV": "ipv_efficiency",
        "Capacité reg solaire installés KW": "regulator_installed_kw",
        "Capacité reg solaire Disponibles KW": "regulator_available_kw",
        "batch": "batch",
        "image Solar": "image_solar",
        "Image GoogleE": "image_google_earth"
    }
)

# ======================================
# 6. Conversion date
# ======================================

if "installation_date" in solar_df.columns:
    solar_df["installation_date"] = pd.to_datetime(
        solar_df["installation_date"],
        errors="coerce"
    ).dt.date

# ======================================
# 7. Colonnes à conserver
# ======================================

columns_to_keep = [
    "site_id",
    "panel_type",
    "panel_power_wc",
    "panel_quantity",
    "total_installed_power_wc",
    "solar_chargers_count",
    "charger_slots",
    "installation_date",
    "panel_condition",
    "ipv_efficiency",
    "regulator_installed_kw",
    "regulator_available_kw",
    "batch",
    "image_solar",
    "image_google_earth"
]

solar_df = solar_df[
    [c for c in columns_to_keep if c in solar_df.columns]
]

# ======================================
# 8. Contrôle avant import
# ======================================

print("\nColonnes à importer :")
print(solar_df.columns.tolist())

print("\nAperçu :")
print(solar_df.head())

# ======================================
# 9. Import PostgreSQL
# ======================================

solar_df.to_sql(
    "solar_installations",
    engine,
    if_exists="append",
    index=False,
    method="multi"
)

print(
    f"\n✅ {len(solar_df)} installations solaires importées"
)