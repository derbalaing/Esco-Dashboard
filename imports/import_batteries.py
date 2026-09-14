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


def create_battery_table():

    sql = text("""
    CREATE TABLE IF NOT EXISTS battery_installations
    (
        battery_installation_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES sites(site_id),

        battery_type VARCHAR(50) NOT NULL,

        nb_battery INTEGER NOT NULL,
        capacity_ah NUMERIC(10,2) NOT NULL,

        nominal_voltage NUMERIC(10,2) DEFAULT 48,
        efficiency_pct NUMERIC(5,2) DEFAULT 95,

        battery_quality_pct NUMERIC(5,2) DEFAULT 100,
        dod_pct NUMERIC(5,2) DEFAULT 80,

        soc_initial_pct NUMERIC(5,2) DEFAULT 80,

        soc_start_ge_pct NUMERIC(5,2) DEFAULT 50,
        soc_stop_ge_pct NUMERIC(5,2) DEFAULT 95,

        soc_start_charge_pct NUMERIC(5,2) DEFAULT 50,
        soc_stop_charge_pct NUMERIC(5,2) DEFAULT 95,

        k1 NUMERIC(6,3) DEFAULT 0.20,
        k2 NUMERIC(6,3) DEFAULT 0.05,

        status VARCHAR(30) DEFAULT 'ACTIVE',

        installation_date DATE,

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        CONSTRAINT uq_battery_site UNIQUE (site_id)
    );
    """)

    with engine.begin() as conn:
        conn.execute(sql)


def normalize_columns(df):

    df = df.copy()

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace("%", "pct")
    )

    return df


def import_batteries_excel(file_path="data/Batteries.xlsx"):

    create_battery_table()

    df = pd.read_excel(file_path)
    df = normalize_columns(df)

    required_columns = [
        "code_site",
        "battery_type",
        "nb_battery",
        "capacity_ah",
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

    defaults = {
        "battery_brand": None,
        "battery_model_type": None,
        "nominal_voltage": 48,
        "efficiency_pct": 95,
        "battery_quality_pct": 100,
        "dod_pct": 80,
        "soc_initial_pct": 80,
        "soc_start_ge_pct": 50,
        "soc_stop_ge_pct": 95,
        "soc_start_charge_pct": 50,
        "soc_stop_charge_pct": 95,
        "k1": 0.20,
        "k2": 0.05,
        "status": "ACTIVE",
        "installation_date": "01/01/2025",

    }

    for col, value in defaults.items():
        if col not in df.columns:
            df[col] = value

    df["battery_type"] = (
        df["battery_type"]
        .astype(str)
        .str.strip()
        .str.upper()
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

    sql = text("""
    INSERT INTO battery_installations
    (
        site_id,
        battery_type,
        battery_brand,
        battery_model_type,
        nb_battery,
        capacity_ah,
        nominal_voltage,
        efficiency_pct,
        battery_quality_pct,
        dod_pct,
        soc_initial_pct,
        soc_start_ge_pct,
        soc_stop_ge_pct,
        soc_start_charge_pct,
        soc_stop_charge_pct,
        k1,
        k2,
        status,
        installation_date,
        updated_at
    )
    VALUES
    (
        :site_id,
        :battery_type,
        :battery_brand,
        :battery_model_type,
        :nb_battery,
        :capacity_ah,
        :nominal_voltage,
        :efficiency_pct,
        :battery_quality_pct,
        :dod_pct,
        :soc_initial_pct,
        :soc_start_ge_pct,
        :soc_stop_ge_pct,
        :soc_start_charge_pct,
        :soc_stop_charge_pct,
        :k1,
        :k2,
        :status,
        :installation_date,
        NOW()
    )
    ON CONFLICT (site_id)
    DO UPDATE SET
        battery_type = EXCLUDED.battery_type,
        battery_brand = EXCLUDED.battery_brand,
        battery_model_type = EXCLUDED.battery_model_type,
        nb_battery = EXCLUDED.nb_battery,
        capacity_ah = EXCLUDED.capacity_ah,
        nominal_voltage = EXCLUDED.nominal_voltage,
        efficiency_pct = EXCLUDED.efficiency_pct,
        battery_quality_pct = EXCLUDED.battery_quality_pct,
        dod_pct = EXCLUDED.dod_pct,
        soc_initial_pct = EXCLUDED.soc_initial_pct,
        soc_start_ge_pct = EXCLUDED.soc_start_ge_pct,
        soc_stop_ge_pct = EXCLUDED.soc_stop_ge_pct,
        soc_start_charge_pct = EXCLUDED.soc_start_charge_pct,
        soc_stop_charge_pct = EXCLUDED.soc_stop_charge_pct,
        k1 = EXCLUDED.k1,
        k2 = EXCLUDED.k2,
        status = EXCLUDED.status,
        installation_date = EXCLUDED.installation_date,
        updated_at = NOW();
    """)

    records = df[
        [
            "site_id",
            "battery_type",
            "battery_brand",
            "battery_model_type",
            "nb_battery",
            "capacity_ah",
            "nominal_voltage",
            "efficiency_pct",
            "battery_quality_pct",
            "dod_pct",
            "soc_initial_pct",
            "soc_start_ge_pct",
            "soc_stop_ge_pct",
            "soc_start_charge_pct",
            "soc_stop_charge_pct",
            "k1",
            "k2",
            "status",
            "installation_date",
        ]
    ].to_dict(orient="records")

    with engine.begin() as conn:
        conn.execute(sql, records)

    print("✅ Import batteries terminé")
    print("Lignes importées :", len(records))
    print("Sites importés :", df["code_site"].nunique())


if __name__ == "__main__":
    import_batteries_excel("data/Batteries.xlsx")