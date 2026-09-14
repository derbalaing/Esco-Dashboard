# imports/import_sites.py





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

# =========================
# 1. Lecture du fichier Excel
# =========================

sites_df = pd.read_excel("data/Sites.xlsx")

# =========================
# 2. Lecture des équipes depuis PostgreSQL
# =========================

teams_df = pd.read_sql(
    "SELECT team_id, team_name FROM teams",
    engine
)

# =========================
# 3. Correspondance Equipe -> team_id
# =========================

sites_df = sites_df.merge(
    teams_df,
    left_on="Equipe",
    right_on="team_name",
    how="left"
)

# =========================
# 4. Vérification équipes manquantes
# =========================

missing = sites_df[sites_df["team_id"].isna()]

if not missing.empty:
    print("\nEquipes non trouvées :")
    print(missing["Equipe"].unique())
    raise Exception(
        "Certaines équipes n'existent pas dans la table teams"
    )

# =========================
# 5. Renommage des colonnes
# =========================

sites_df = sites_df.rename(
    columns={
        "Code site": "code_site",
        "Code Site OCI": "code_site_oci",
        "Nom du site": "site_name",
        "Zone notification": "zone_notification",
        "Localisation du site": "localisation",
        "Longitutde": "longitude",
        "Lattitude": "latitude",
        "Autonomie contractuelle": "autonomie_contractuelle",
        "Catégorie": "categorie",
        "Priorité": "priorite",
        "SLA": "sla",
        "Indoor/Outdoor": "indoor_outdoor",
        "Puissance contractuelle": "puissance_contractuelle_w",
        "Typologie facturée Juin 26": "typologie_facturee",
        "Typologie FMS": "typologie_fms",
        "Type de site": "type_site",
        "Distance base - site [Km]": "distance_base_site_km",
        "Description situation géographique": "description_geo",
        "Remote": "remote_name",
        "Informations sup": "additional_info",
        "Image site1": "image_site1",
        "Image site2": "image_site2",
        "Image site3": "image_site3",
        "Image site4": "image_site4",
        "Image site5": "image_site5"
    }
)

# =========================
# 6. Suppression colonnes inutiles
# =========================

cols_to_drop = [
    "Equipe",
    "team_name"
]

for col in cols_to_drop:
    if col in sites_df.columns:
        sites_df.drop(columns=[col], inplace=True)

# =========================
# 7. Garder uniquement les colonnes existantes
# =========================

valid_columns = [
    "code_site",
    "code_site_oci",
    "site_name",
    "team_id",
    "zone_notification",
    "localisation",
    "longitude",
    "latitude",
    "autonomie_contractuelle",
    "categorie",
    "priorite",
    "sla",
    "indoor_outdoor",
    "puissance_contractuelle_w",
    "typologie_facturee",
    "typologie_fms",
    "type_site",
    "distance_base_site_km",
    "description_geo",
    "remote_name",
    "additional_info",
    "image_site1",
    "image_site2",
    "image_site3",
    "image_site4",
    "image_site5"
]

sites_df = sites_df[
    [c for c in valid_columns if c in sites_df.columns]
]

# =========================
# 8. Import PostgreSQL
# =========================

sites_df.to_sql(
    "sites",
    engine,
    if_exists="append",
    index=False,
    method="multi"
)

print(f"{len(sites_df)} sites importés avec succès")