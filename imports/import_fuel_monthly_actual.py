import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.database import engine


DEFAULT_FILE_PATH = "data/Fuel_Monthly_Actual.xlsx"


def normalize_month(value):
    if pd.isna(value):
        return None

    dt = pd.to_datetime(
        value,
        errors="coerce"
    )

    if pd.isna(dt):
        return None

    return dt.replace(day=1).date()


def import_fuel_monthly_actual(file_path=DEFAULT_FILE_PATH):

    print(f"📥 Lecture fichier : {file_path}")

    df = pd.read_excel(file_path)

    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    required_cols = [
        "code_site",
        "fuel_month",
        "actual_fuel_l",
    ]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(
                f"Colonne obligatoire manquante : {col}"
            )

    if "comment" not in df.columns:
        df["comment"] = None

    df["code_site"] = (
        df["code_site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["fuel_month"] = df["fuel_month"].apply(
        normalize_month
    )

    df["actual_fuel_l"] = pd.to_numeric(
        df["actual_fuel_l"],
        errors="coerce"
    ).fillna(0)

    df = df[
        df["fuel_month"].notna()
    ].copy()

    sites_sql = text("""
    SELECT
        site_id,
        UPPER(TRIM(code_site)) AS code_site
    FROM sites
    """)

    sites_df = pd.read_sql(
        sites_sql,
        engine
    )

    df = df.merge(
        sites_df,
        on="code_site",
        how="left"
    )

    missing_sites = df[
        df["site_id"].isna()
    ].copy()

    if not missing_sites.empty:

        rejected_path = PROJECT_ROOT / "data" / "rejected"
        rejected_path.mkdir(
            parents=True,
            exist_ok=True
        )

        missing_file = rejected_path / "missing_sites_fuel_monthly.xlsx"

        missing_sites.to_excel(
            missing_file,
            index=False
        )

        print(
            f"⚠️ Sites non trouvés exportés : {missing_file}"
        )

    df_valid = df[
        df["site_id"].notna()
    ].copy()

    if df_valid.empty:
        print("⚠️ Aucune ligne valide à importer.")
        return

    records = []

    for _, r in df_valid.iterrows():

        records.append(
            {
                "site_id": int(r["site_id"]),
                "fuel_month": r["fuel_month"],
                "actual_fuel_l": float(r["actual_fuel_l"]),
                "source": "EXCEL_IMPORT",
                "comment": None if pd.isna(r["comment"]) else str(r["comment"]),
            }
        )

    insert_sql = text("""
    INSERT INTO site_fuel_monthly_actual
    (
        site_id,
        fuel_month,
        actual_fuel_l,
        source,
        comment,
        updated_at
    )
    VALUES
    (
        :site_id,
        :fuel_month,
        :actual_fuel_l,
        :source,
        :comment,
        NOW()
    )
    ON CONFLICT (site_id, fuel_month)
    DO UPDATE SET
        actual_fuel_l = EXCLUDED.actual_fuel_l,
        source = EXCLUDED.source,
        comment = EXCLUDED.comment,
        updated_at = NOW();
    """)

    with engine.begin() as conn:
        conn.execute(
            insert_sql,
            records
        )

    print(
        f"✅ Import terminé : {len(records)} lignes fuel mensuel importées."
    )


if __name__ == "__main__":
    import_fuel_monthly_actual()