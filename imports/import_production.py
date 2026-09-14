import pandas as pd
import sys
import os
from sqlalchemy import text

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)


from config.database import engine

# ==========================================
# 1. Lecture du fichier Excel
# ==========================================

df = pd.read_excel("data/Production_Reelle.xlsx")

print(f"Lignes lues : {len(df)}")

# ==========================================
# 2. Lecture des sites depuis PostgreSQL
# ==========================================

sites_df = pd.read_sql(
    """
    SELECT
        site_id,
        code_site
    FROM sites
    """,
    engine
)

# ==========================================
# 3. Correspondance Code Site -> site_id
# ==========================================

df = df.merge(
    sites_df,
    left_on="Site ID",
    right_on="code_site",
    how="left"
)

# ==========================================
# 4. Vérification des sites manquants
# ==========================================

missing = df[df["site_id"].isna()]

if not missing.empty:
    print("\nSites non trouvés :")
    print(missing["Site ID"].unique())

# ==========================================
# 5. Conversion production
# ==========================================

df["Param Value"] = (
    df["Param Value"]
    .astype(str)
    .str.replace(",", ".", regex=False)
)

df["Param Value"] = pd.to_numeric(
    df["Param Value"],
    errors="coerce"
)

# ==========================================
# 6. Détermination du statut
# ==========================================

df["status"] = "NORMAL"

df.loc[
    df["Param Value"].isin([-1, -2]),
    "status"
] = "LOSTCOM"

# ==========================================
# 7. Production réelle
# ==========================================

df["production_kwh"] = df["Param Value"]

df.loc[
    df["status"] == "LOSTCOM",
    "production_kwh"
] = None

# ==========================================
# 8. Conversion date
# ==========================================

df["production_date"] = pd.to_datetime(
    df["Date"],
    errors="coerce"
).dt.date

# ==========================================
# 9. Construction DataFrame final
# ==========================================

df_final = pd.DataFrame({
    "site_id": df["site_id"],
    "production_date": df["production_date"],
    "param_name": df["Param Name"],
    "production_kwh": df["production_kwh"],
    "unit": df["Measure"],
    "status": df["status"]
})

# ==========================================
# 10. Suppression lignes invalides
# ==========================================

df_final = df_final.dropna(
    subset=["site_id", "production_date"]
)

# ==========================================
# 11. Contrôles qualité
# ==========================================

print("\nStatistiques :")

print(f"Total lignes : {len(df_final)}")

print("\nStatus :")
print(df_final["status"].value_counts())

print("\nValeurs nulles :")
print(df_final.isnull().sum())

print("\nAperçu :")
print(df_final.head())


# ==========================================
# 12. Import PostgreSQL avec skip doublons
# ==========================================

# Sécurité : éviter les doublons dans le fichier Excel lui-même
before_dedup = len(df_final)

df_final = df_final.drop_duplicates(
    subset=[
        "site_id",
        "production_date",
    ],
    keep="last"
).copy()

duplicates_in_file = before_dedup - len(df_final)

if duplicates_in_file > 0:
    print(
        f"⚠️ Doublons supprimés dans le fichier Excel : "
        f"{duplicates_in_file}"
    )

# Conversion propre des types
df_final["site_id"] = df_final["site_id"].astype(int)

records = []

for _, r in df_final.iterrows():

    production_kwh = r["production_kwh"]

    if pd.isna(production_kwh):
        production_kwh = None
    else:
        production_kwh = float(production_kwh)

    records.append(
        {
            "site_id": int(r["site_id"]),
            "production_date": r["production_date"],
            "param_name": str(r["param_name"]),
            "production_kwh": production_kwh,
            "unit": str(r["unit"]),
            "status": str(r["status"]),
        }
    )

insert_sql = text("""
INSERT INTO solar_productions
(
    site_id,
    production_date,
    param_name,
    production_kwh,
    unit,
    status
)
VALUES
(
    :site_id,
    :production_date,
    :param_name,
    :production_kwh,
    :unit,
    :status
)
ON CONFLICT (site_id, production_date)
DO NOTHING;
""")

batch_size = 500
inserted_total = 0

for start in range(0, len(records), batch_size):

    end = min(start + batch_size, len(records))
    batch = records[start:end]

    with engine.begin() as conn:

        result = conn.execute(
            insert_sql,
            batch
        )

        if result.rowcount is not None and result.rowcount > 0:
            inserted_total += result.rowcount

    print(
        f"✅ Batch traité : {end}/{len(records)}"
    )

skipped_total = len(records) - inserted_total

print("\nRésumé import production solaire :")
print(f"Total lignes valides préparées : {len(records)}")
print(f"Lignes insérées : {inserted_total}")
print(f"Lignes déjà existantes ignorées : {skipped_total}")