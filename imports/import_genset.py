import pandas as pd
from sqlalchemy import text

import sys
import os

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)


from config.database import engine


# =====================================================
# CREATE TABLE
# =====================================================

def create_genset_table():

    sql = text("""
    CREATE TABLE IF NOT EXISTS genset_installations
    (
        genset_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES sites(site_id),

        brand VARCHAR(100),
        model VARCHAR(100),

        rated_power_kva NUMERIC(10,2),
        rated_power_kw NUMERIC(10,2),

        fuel_tank_l NUMERIC(10,2),

        fuel_25_lph NUMERIC(10,3),
        fuel_50_lph NUMERIC(10,3),
        fuel_75_lph NUMERIC(10,3),
        fuel_100_lph NUMERIC(10,3),

        status VARCHAR(30) DEFAULT 'ACTIVE',

        installation_date DATE,

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        CONSTRAINT uq_genset_site UNIQUE (site_id)
    );
    """)

    with engine.begin() as conn:
        conn.execute(sql)


# =====================================================
# NORMALIZE COLUMNS
# =====================================================

def normalize_columns(df):

    df = df.copy()

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    return df


# =====================================================
# IMPORT GE EXCEL
# =====================================================

def import_genset_excel(file_path="data/GE.xlsx"):

    create_genset_table()

    df = pd.read_excel(file_path)

    df = normalize_columns(df)

    required_columns = [
        "code_site",
        "rated_power_kva",
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Colonnes obligatoires manquantes : {missing}"
        )

    df["code_site"] = (
        df["code_site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # =====================================================
    # GET SITE ID FROM sites TABLE
    # =====================================================

    sites = pd.read_sql(
        """
        SELECT
            site_id,
            UPPER(TRIM(code_site)) AS code_site
        FROM sites
        """,
        engine
    )

    df = df.merge(
        sites,
        on="code_site",
        how="left"
    )

    missing_sites = df[df["site_id"].isna()]

    if not missing_sites.empty:
        raise ValueError(
            "Sites non trouvés dans la table sites : "
            + ", ".join(missing_sites["code_site"].unique())
        )

    # =====================================================
    # DEFAULT COLUMNS
    # =====================================================

    optional_columns = {
        "brand": None,
        "model": None,
        "rated_power_kw": None,
        "fuel_tank_l": None,
        "fuel_25_lph": None,
        "fuel_50_lph": None,
        "fuel_75_lph": None,
        "fuel_100_lph": None,
        "status": "ACTIVE",
        "installation_date": None,
    }

    for col, default_value in optional_columns.items():

        if col not in df.columns:
            df[col] = default_value

    # Si rated_power_kw est vide, on applique cos phi = 0.8
    df["rated_power_kw"] = df["rated_power_kw"].fillna(
        df["rated_power_kva"] * 0.8
    )

    # Courbe fuel par défaut
    df["fuel_25_lph"] = df["fuel_25_lph"].fillna(1.3)
    df["fuel_50_lph"] = df["fuel_50_lph"].fillna(2.0)
    df["fuel_75_lph"] = df["fuel_75_lph"].fillna(2.8)
    df["fuel_100_lph"] = df["fuel_100_lph"].fillna(3.7)

    df["status"] = (
        df["status"]
        .fillna("ACTIVE")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["installation_date"] = pd.to_datetime(
        df["installation_date"],
        errors="coerce"
    ).dt.date

    # =====================================================
    # INSERT / UPDATE
    # =====================================================

    sql = text("""
    INSERT INTO genset_installations
    (
        site_id,
        brand,
        model,
        rated_power_kva,
        rated_power_kw,
        fuel_tank_l,
        fuel_25_lph,
        fuel_50_lph,
        fuel_75_lph,
        fuel_100_lph,
        status,
        installation_date,
        updated_at
    )
    VALUES
    (
        :site_id,
        :brand,
        :model,
        :rated_power_kva,
        :rated_power_kw,
        :fuel_tank_l,
        :fuel_25_lph,
        :fuel_50_lph,
        :fuel_75_lph,
        :fuel_100_lph,
        :status,
        :installation_date,
        NOW()
    )
    ON CONFLICT (site_id)
    DO UPDATE SET
        brand = EXCLUDED.brand,
        model = EXCLUDED.model,
        rated_power_kva = EXCLUDED.rated_power_kva,
        rated_power_kw = EXCLUDED.rated_power_kw,
        fuel_tank_l = EXCLUDED.fuel_tank_l,
        fuel_25_lph = EXCLUDED.fuel_25_lph,
        fuel_50_lph = EXCLUDED.fuel_50_lph,
        fuel_75_lph = EXCLUDED.fuel_75_lph,
        fuel_100_lph = EXCLUDED.fuel_100_lph,
        status = EXCLUDED.status,
        installation_date = EXCLUDED.installation_date,
        updated_at = NOW();
    """)

    records = df[
        [
            "site_id",
            "brand",
            "model",
            "rated_power_kva",
            "rated_power_kw",
            "fuel_tank_l",
            "fuel_25_lph",
            "fuel_50_lph",
            "fuel_75_lph",
            "fuel_100_lph",
            "status",
            "installation_date",
        ]
    ].to_dict(orient="records")

    with engine.begin() as conn:
        conn.execute(sql, records)

    print("✅ Import GE terminé")
    print("Lignes importées :", len(records))
    print("Sites importés :", df["code_site"].nunique())


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    import_genset_excel("data/GE.xlsx")