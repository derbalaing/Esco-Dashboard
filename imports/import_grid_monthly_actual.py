import pandas as pd
import sys
import os
from pathlib import Path
from sqlalchemy import text



# Ajouter la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from config.database import engine


FILE_PATH = "data/Grid_Monthly_Actual.xlsx"


def parse_month(value):
    """
    Convertit une date Excel / texte vers le premier jour du mois.
    Exemple :
    2026-07-15 -> 2026-07-01
    2026-07-01 -> 2026-07-01
    """
    if pd.isna(value):
        return None

    dt = pd.to_datetime(value, errors="coerce")

    if pd.isna(dt):
        return None

    return dt.to_period("M").to_timestamp().date()


def main():

    print("====================================")
    print("IMPORT CONSOMMATION GRID RÉELLE")
    print("====================================")

    df = pd.read_excel(FILE_PATH)

    print(f"Lignes lues : {len(df)}")

    required_cols = [
        "code_site",
        "grid_month",
        "actual_grid_kwh",
    ]

    missing_cols = [
        col for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            f"Colonnes manquantes dans le fichier Excel : {missing_cols}"
        )

    df["code_site"] = (
        df["code_site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["grid_month"] = df["grid_month"].apply(parse_month)

    df["actual_grid_kwh"] = (
        df["actual_grid_kwh"]
        .astype(str)
        .str.replace(",", ".", regex=False)
    )

    df["actual_grid_kwh"] = pd.to_numeric(
        df["actual_grid_kwh"],
        errors="coerce"
    )

    if "comment" not in df.columns:
        df["comment"] = None

    df["comment"] = df["comment"].fillna("").astype(str)

    # Suppression lignes invalides
    df = df.dropna(
        subset=[
            "code_site",
            "grid_month",
            "actual_grid_kwh",
        ]
    ).copy()

    print(f"Lignes valides après nettoyage : {len(df)}")

    # Charger les sites
    sites_df = pd.read_sql(
        """
        SELECT
            site_id,
            UPPER(TRIM(code_site)) AS code_site
        FROM sites
        """,
        engine
    )

    df = df.merge(
        sites_df,
        on="code_site",
        how="left"
    )

    missing_sites = df[df["site_id"].isna()].copy()

    if not missing_sites.empty:

        rejected_dir = Path("data/rejected")
        rejected_dir.mkdir(parents=True, exist_ok=True)

        rejected_file = rejected_dir / "missing_sites_grid_monthly_actual.xlsx"

        missing_sites.to_excel(
            rejected_file,
            index=False
        )

        print("\nSites non trouvés :")
        print(missing_sites["code_site"].unique())

        print(f"\nFichier rejet généré : {rejected_file}")

    df = df.dropna(subset=["site_id"]).copy()

    df["site_id"] = df["site_id"].astype(int)

    # Éviter doublons dans le fichier Excel
    before_dedup = len(df)

    df = df.drop_duplicates(
        subset=[
            "site_id",
            "grid_month",
        ],
        keep="last"
    ).copy()

    duplicates = before_dedup - len(df)

    if duplicates > 0:
        print(f"⚠️ Doublons supprimés dans le fichier : {duplicates}")

    records = []

    for _, r in df.iterrows():

        records.append(
            {
                "site_id": int(r["site_id"]),
                "grid_month": r["grid_month"],
                "actual_grid_kwh": float(r["actual_grid_kwh"]),
                "source": "EXCEL",
                "comment": r["comment"],
            }
        )

    insert_sql = text("""
    INSERT INTO site_grid_monthly_actual
    (
        site_id,
        grid_month,
        actual_grid_kwh,
        source,
        comment,
        updated_at
    )
    VALUES
    (
        :site_id,
        :grid_month,
        :actual_grid_kwh,
        :source,
        :comment,
        NOW()
    )
    ON CONFLICT (site_id, grid_month)
    DO UPDATE SET
        actual_grid_kwh = EXCLUDED.actual_grid_kwh,
        source = EXCLUDED.source,
        comment = EXCLUDED.comment,
        updated_at = NOW();
    """)

    batch_size = 500
    total_imported = 0

    for start in range(0, len(records), batch_size):

        end = min(start + batch_size, len(records))
        batch = records[start:end]

        with engine.begin() as conn:
            conn.execute(insert_sql, batch)

        total_imported += len(batch)

        print(f"✅ Batch importé : {end}/{len(records)}")

    print("\n====================================")
    print("IMPORT TERMINÉ")
    print("====================================")
    print(f"Lignes importées / mises à jour : {total_imported}")


if __name__ == "__main__":
    main()