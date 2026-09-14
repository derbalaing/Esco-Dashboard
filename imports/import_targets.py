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
# 1. Lecture Excel
# ======================================

df = pd.read_excel("data/Target_Solar.xlsx")


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
# 3. Transformation des colonnes mois
# ======================================

month_mapping = {
    "Jan": 1,
    "févr": 2,
    "mars": 3,
    "avr": 4,
    "mai": 5,
    "juin": 6,
    "juil": 7,
    "août": 8,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "déc": 12
}

df_long = pd.melt(
    df,
    id_vars=["Code site"],
    value_vars=list(month_mapping.keys()),
    var_name="month_name",
    value_name="target_kwh_kwc_day"
)


print(df_long[df_long["target_kwh_kwc_day"].isna()])

df_long["month_number"] = (
    df_long["month_name"]
    .map(month_mapping)
)

# ======================================
# 4. Correspondance site_id
# ======================================

df_long = df_long.merge(
    sites_df,
    left_on="Code site",
    right_on="code_site",
    how="left"
)

# ======================================
# 5. Vérification
# ======================================

missing = df_long[df_long["site_id"].isna()]

if not missing.empty:
    print("Sites non trouvés :")
    print(missing["Code site"].unique())

# ======================================
# 6. Colonnes finales
# ======================================

df_long = df_long[
    [
        "site_id",
        "month_number",
        "target_kwh_kwc_day"
    ]
]

# ======================================
# 7. Import PostgreSQL
# ======================================

df_long.to_sql(
    "solar_targets",
    engine,
    if_exists="append",
    index=False,
    method="multi"
)

print(
    f"{len(df_long)} targets importés"
)