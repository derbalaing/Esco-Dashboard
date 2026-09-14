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

def create_powercore_table():

    sql = text("""
    CREATE TABLE IF NOT EXISTS powercore_installations
    (
        powercore_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES sites(site_id),

        powercore_brand VARCHAR(100),
        powercore_model VARCHAR(100),

        nominal_voltage_v NUMERIC(10,2) DEFAULT 48,

        nb_rectifiers INTEGER,
        rectifier_current_a NUMERIC(10,2),
        total_current_a NUMERIC(10,2),

        rectifier_power_kw NUMERIC(10,2),
        total_power_kw NUMERIC(10,2),

        efficiency_pct NUMERIC(5,2) DEFAULT 95,

        status VARCHAR(30) DEFAULT 'ACTIVE',

        installation_date DATE,

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        CONSTRAINT uq_powercore_site UNIQUE (site_id)
    );
    """)

    index_sql = text("""
    CREATE INDEX IF NOT EXISTS idx_powercore_installations_site
    ON powercore_installations(site_id);
    """)

    with engine.begin() as conn:
        conn.execute(sql)
        conn.execute(index_sql)


# =====================================================
# NORMALIZE COLUMNS
# =====================================================

def normalize_columns(df):

    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace("%", "pct")
        .str.replace("(", "", regex=False)
        .str.replace(")", "", regex=False)
    )

    return df


# =====================================================
# IMPORT POWERCORE EXCEL
# =====================================================

def import_powercore_excel(file_path="data/Powercore.xlsx"):

    create_powercore_table()

    df = pd.read_excel(file_path)
    df = normalize_columns(df)

    required_columns = [
        "code_site",
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
    # GET site_id FROM sites
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
            + ", ".join(missing_sites["code_site"].astype(str).unique())
        )

    # =====================================================
    # DEFAULT COLUMNS
    # =====================================================

    defaults = {
        "powercore_brand": None,
        "powercore_model": None,
        "nominal_voltage_v": 48,
        "nb_rectifiers": None,
        "rectifier_current_a": None,
        "total_current_a": None,
        "rectifier_power_kw": None,
        "total_power_kw": None,
        "efficiency_pct": 95,
        "status": "ACTIVE",
        "installation_date": "01/01/2025",
    }

    for col, default_value in defaults.items():
        if col not in df.columns:
            df[col] = default_value

    numeric_columns = [
        "nominal_voltage_v",
        "nb_rectifiers",
        "rectifier_current_a",
        "total_current_a",
        "rectifier_power_kw",
        "total_power_kw",
        "efficiency_pct",
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df["nominal_voltage_v"] = df["nominal_voltage_v"].fillna(48)
    df["efficiency_pct"] = df["efficiency_pct"].fillna(95)

    # =====================================================
    # CALCULS AUTOMATIQUES
    # =====================================================

    # total_current_a = nb_rectifiers × rectifier_current_a
    mask_total_current = (
        df["total_current_a"].isna()
        & df["nb_rectifiers"].notna()
        & df["rectifier_current_a"].notna()
    )

    df.loc[mask_total_current, "total_current_a"] = (
        df.loc[mask_total_current, "nb_rectifiers"]
        *
        df.loc[mask_total_current, "rectifier_current_a"]
    )

    # rectifier_power_kw = rectifier_current_a × voltage / 1000
    mask_rectifier_power = (
        df["rectifier_power_kw"].isna()
        & df["rectifier_current_a"].notna()
        & df["nominal_voltage_v"].notna()
    )

    df.loc[mask_rectifier_power, "rectifier_power_kw"] = (
        df.loc[mask_rectifier_power, "rectifier_current_a"]
        *
        df.loc[mask_rectifier_power, "nominal_voltage_v"]
        / 1000
    )

    # total_power_kw = total_current_a × voltage / 1000
    mask_total_power = (
        df["total_power_kw"].isna()
        & df["total_current_a"].notna()
        & df["nominal_voltage_v"].notna()
    )

    df.loc[mask_total_power, "total_power_kw"] = (
        df.loc[mask_total_power, "total_current_a"]
        *
        df.loc[mask_total_power, "nominal_voltage_v"]
        / 1000
    )

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

    df = df.where(
        pd.notnull(df),
        None
    )

    # =====================================================
    # INSERT / UPDATE
    # =====================================================

    sql = text("""
    INSERT INTO powercore_installations
    (
        site_id,
        powercore_brand,
        powercore_model,
        nominal_voltage_v,
        nb_rectifiers,
        rectifier_current_a,
        total_current_a,
        rectifier_power_kw,
        total_power_kw,
        efficiency_pct,
        status,
        installation_date,
        updated_at
    )
    VALUES
    (
        :site_id,
        :powercore_brand,
        :powercore_model,
        :nominal_voltage_v,
        :nb_rectifiers,
        :rectifier_current_a,
        :total_current_a,
        :rectifier_power_kw,
        :total_power_kw,
        :efficiency_pct,
        :status,
        :installation_date,
        NOW()
    )
    ON CONFLICT (site_id)
    DO UPDATE SET
        powercore_brand = EXCLUDED.powercore_brand,
        powercore_model = EXCLUDED.powercore_model,
        nominal_voltage_v = EXCLUDED.nominal_voltage_v,
        nb_rectifiers = EXCLUDED.nb_rectifiers,
        rectifier_current_a = EXCLUDED.rectifier_current_a,
        total_current_a = EXCLUDED.total_current_a,
        rectifier_power_kw = EXCLUDED.rectifier_power_kw,
        total_power_kw = EXCLUDED.total_power_kw,
        efficiency_pct = EXCLUDED.efficiency_pct,
        status = EXCLUDED.status,
        installation_date = EXCLUDED.installation_date,
        updated_at = NOW();
    """)

    records = df[
        [
            "site_id",
            "powercore_brand",
            "powercore_model",
            "nominal_voltage_v",
            "nb_rectifiers",
            "rectifier_current_a",
            "total_current_a",
            "rectifier_power_kw",
            "total_power_kw",
            "efficiency_pct",
            "status",
            "installation_date",
        ]
    ].to_dict(orient="records")

    with engine.begin() as conn:
        conn.execute(sql, records)

    print("✅ Import Powercore terminé")
    print("Lignes importées :", len(records))
    print("Sites importés :", df["code_site"].nunique())


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    import_powercore_excel("data/Powercore.xlsx")