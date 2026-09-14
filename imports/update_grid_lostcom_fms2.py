import re
from datetime import datetime, date
from pathlib import Path
import time
from sqlalchemy.exc import OperationalError
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
# CONFIG FICHIER
# =====================================================

DEFAULT_FILE_PATH = "data/Grid_2.xlsx"

# A adapter si nécessaire selon le fichier FMS-2
CODE_SITE_COL_LETTER = "B"
GRID_DATE_COL_LETTER = "D"
GRID_AVAILABILITY_COL_LETTER = "E"

REJECTED_DIR = Path("data/rejected")
REJECTED_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================
# OUTILS
# =====================================================

def col_letter_to_index(letter):
    """
    A -> 0, B -> 1, C -> 2 ...
    """
    letter = letter.upper().strip()
    index = 0

    for char in letter:
        index = index * 26 + ord(char) - ord("A") + 1

    return index - 1


def get_column_by_letter(df, letter):
    idx = col_letter_to_index(letter)

    if idx >= df.shape[1]:
        raise ValueError(
            f"La colonne {letter} n'existe pas dans le fichier. "
            f"Nombre de colonnes détectées : {df.shape[1]}"
        )

    return df.iloc[:, idx]


def to_number(value):
    if pd.isna(value):
        return None

    s = str(value).strip()

    if s == "" or s.upper() in ["NAN", "NONE", "NULL", "-"]:
        return None

    s = s.replace("%", "")
    s = s.replace(" ", "")
    s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return None


def parse_excel_date(value):
    """
    Lecture robuste des dates :
    - 2026-07-01 => 1 juillet 2026
    - 01/07/2026 => 1 juillet 2026
    - date Excel numérique
    """

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.date()

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, (int, float)):
        try:
            dt = pd.to_datetime(
                value,
                unit="D",
                origin="1899-12-30",
                errors="coerce"
            )

            if pd.isna(dt):
                return None

            return dt.date()

        except Exception:
            return None

    s = str(value).strip()

    if s == "" or s.upper() in ["NAN", "NONE", "NULL"]:
        return None

    s10 = s[:10]

    # Format ISO : 2026-07-01
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", s10):
        s10 = s10.replace("/", "-")

        dt = pd.to_datetime(
            s10,
            format="%Y-%m-%d",
            errors="coerce"
        )

        if pd.isna(dt):
            return None

        return dt.date()

    # Format français : 01/07/2026
    if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$", s10):
        dt = pd.to_datetime(
            s10,
            dayfirst=True,
            errors="coerce"
        )

        if pd.isna(dt):
            return None

        return dt.date()

    dt = pd.to_datetime(
        s,
        errors="coerce"
    )

    if pd.isna(dt):
        return None

    return dt.date()


def read_excel_or_html(file_path):
    """
    Certains exports .xls FMS sont en réalité des fichiers HTML.
    Cette fonction essaye Excel puis HTML.
    """

    try:
        return pd.read_excel(
            file_path,
            header=None
        )

    except Exception as e1:

        try:
            tables = pd.read_html(file_path)

            if len(tables) == 0:
                raise ValueError("Aucune table trouvée dans le fichier HTML.")

            return tables[0]

        except Exception as e2:
            raise Exception(
                f"Impossible de lire le fichier Excel/HTML.\n"
                f"Erreur Excel : {e1}\n"
                f"Erreur HTML : {e2}"
            )


def normalize_availability(value):
    availability = to_number(value)

    if availability is None:
        return None

    # Si le fichier donne 0.95 au lieu de 95 %
    if 0 <= availability <= 1:
        availability = availability * 100

    if availability < 0:
        availability = 0

    if availability > 100:
        availability = 100

    return round(availability, 2)


def outage_from_availability(availability):
    """
    Règle demandée :
    disponibilité = 100 => 0 coupure
    sinon => 1 coupure
    """

    if availability is None:
        return None

    if availability >= 100:
        return 0

    return 1


def compute_fms2_grid_mode(availability):

    if availability is None:
        return {
            "grid_mode": None,
            "grid_availability_pct": None,
            "grid_outages_per_day": None,
            "source": "FMS-2",
            "status": None,
        }

    # Si FMS-2 confirme disponibilité 0 %
    # le site reste / devient OFF_GRID
    if availability <= 0:
        return {
            "grid_mode": "OFF_GRID",
            "grid_availability_pct": 0,
            "grid_outages_per_day": 0,
            "source": "FMS-2",
            "status": "ACTIVE",
        }

    # Si disponibilité 100 %
    if availability >= 100:
        return {
            "grid_mode": "ON_GRID",
            "grid_availability_pct": 100,
            "grid_outages_per_day": 0,
            "source": "FMS-2",
            "status": "ACTIVE",
        }

    # Si disponibilité partielle
    return {
        "grid_mode": "ON_GRID",
        "grid_availability_pct": availability,
        "grid_outages_per_day": 1,
        "source": "FMS-2",
        "status": "ACTIVE",
    }

# =====================================================
# UPDATE GRID LOSTCOM
# =====================================================

def update_grid_lostcom_from_fms2(file_path=DEFAULT_FILE_PATH):

    print("=" * 80)
    print("Mise à jour site_grid LOSTCOM depuis FMS-2")
    print("=" * 80)

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {file_path}"
        )

    df_raw = read_excel_or_html(file_path)

    print(f"Fichier lu : {file_path}")
    print(f"Dimensions fichier : {df_raw.shape[0]} lignes x {df_raw.shape[1]} colonnes")

    df = pd.DataFrame()

    df["code_site"] = get_column_by_letter(
        df_raw,
        CODE_SITE_COL_LETTER
    )

    df["grid_date"] = get_column_by_letter(
        df_raw,
        GRID_DATE_COL_LETTER
    )

    df["grid_availability_raw"] = get_column_by_letter(
        df_raw,
        GRID_AVAILABILITY_COL_LETTER
    )

    # Nettoyage
    df["code_site"] = (
        df["code_site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["grid_date"] = df["grid_date"].apply(
        parse_excel_date
    )

    df["grid_availability_pct"] = df["grid_availability_raw"].apply(
        normalize_availability
    )

    df = df[
        (df["code_site"].notna())
        &
        (df["code_site"] != "")
        &
        (df["code_site"] != "NAN")
        &
        (df["grid_date"].notna())
        &
        (df["grid_availability_pct"].notna())
        &
        (~df["code_site"].isin(
            [
                "CODE_SITE",
                "CODE SITE",
                "SITE",
                "SITES",
                "NOM SITE",
                "SITE NAME",
            ]
        ))
    ].copy()

    if df.empty:
        print("⚠️ Aucune ligne valide trouvée dans le fichier.")
        return

    df["grid_outages_per_day"] = df["grid_availability_pct"].apply(
        outage_from_availability
    )

    df["grid_mode"] = "ON_GRID"
    df["source"] = "FMS-2"
    df["status"] = "ACTIVE"

    # Dedup fichier par code_site + date
    df = df.drop_duplicates(
        subset=[
            "code_site",
            "grid_date",
        ],
        keep="last"
    )

    print(f"Lignes valides dans le fichier FMS-2 : {len(df)}")

    # =====================================================
    # MERGE AVEC SITES
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

    missing_sites = df[
        df["site_id"].isna()
    ].copy()

    if not missing_sites.empty:

        rejected_file = REJECTED_DIR / "missing_sites_grid_fms2.xlsx"

        missing_sites[
            [
                "code_site",
                "grid_date",
                "grid_availability_raw",
                "grid_availability_pct",
            ]
        ].to_excel(
            rejected_file,
            index=False
        )

        print("⚠️ Sites non trouvés dans la table sites :")
        print(
            ", ".join(
                sorted(
                    missing_sites["code_site"].dropna().unique()
                )
            )
        )

        print(f"📄 Fichier rejeté créé : {rejected_file}")

    df = df[
        df["site_id"].notna()
    ].copy()

    df["site_id"] = df["site_id"].astype(int)

    if df.empty:
        print("⚠️ Aucune ligne avec site connu.")
        return

    # =====================================================
    # VERIFIER UNIQUEMENT LES LIGNES ACTUELLEMENT LOSTCOM
    # =====================================================

# =====================================================
# VERIFIER LES LIGNES ACTUELLEMENT LOSTCOM OU OFF_GRID
# =====================================================

    grid_to_check = pd.read_sql(
        """
        SELECT
            grid_id,
            site_id,
            grid_date,
            grid_mode AS old_grid_mode,
            status AS old_status
        FROM site_grid
        WHERE COALESCE(UPPER(TRIM(grid_mode)), '') IN ('LOSTCOM', 'OFF_GRID')
        """,
        engine
    )

    if grid_to_check.empty:
        print("✅ Aucune ligne LOSTCOM ou OFF_GRID dans site_grid.")
        return

    grid_to_check["grid_date"] = pd.to_datetime(
        grid_to_check["grid_date"]
    ).dt.date

    if grid_to_check.empty:
        print("✅ Aucune ligne LOSTCOM dans site_grid.")
        return

    grid_to_check["grid_date"] = pd.to_datetime(
        grid_to_check["grid_date"]
    ).dt.date

    df_to_update = df.merge(
        grid_to_check[
            [
                "site_id",
                "grid_date",
                "old_grid_mode",
                "old_status",
            ]
        ],
        on=[
            "site_id",
            "grid_date",
        ],
        how="inner"
    )

    if df_to_update.empty:
        print(
            "⚠️ Aucune correspondance trouvée entre le fichier FMS-2 "
            "et les lignes LOSTCOM de site_grid."
        )
        return

    df_to_update = df_to_update.drop_duplicates(
        subset=[
            "site_id",
            "grid_date",
        ],
        keep="last"
    )

    # Recalculer le statut Grid à partir de la disponibilité FMS-2
    df_status = df_to_update["grid_availability_pct"].apply(
        compute_fms2_grid_mode
    ).apply(pd.Series)

    df_to_update["grid_mode"] = df_status["grid_mode"]
    df_to_update["grid_availability_pct"] = df_status["grid_availability_pct"]
    df_to_update["grid_outages_per_day"] = df_status["grid_outages_per_day"]
    df_to_update["source"] = df_status["source"]
    df_to_update["status"] = df_status["status"]

    # Garder uniquement les lignes exploitables
    df_to_update = df_to_update[
        df_to_update["status"].notna()
    ].copy()

    print(f"Lignes LOSTCOM / OFF_GRID à vérifier : {len(df_to_update)}")

    print(
        df_to_update.groupby(
            [
                "old_grid_mode",
                "grid_mode",
                "status",
            ]
        )
        .size()
        .reset_index(name="count")
    )

    # =====================================================
    # UPDATE SQL
    # =====================================================

    update_sql = text("""
    UPDATE site_grid
    SET
        grid_mode = :grid_mode,
        grid_availability_pct = :grid_availability_pct,
        grid_outages_per_day = :grid_outages_per_day,
        source = :source,
        status = :status,
        updated_at = NOW()
    WHERE site_id = :site_id
    AND grid_date = :grid_date
    AND COALESCE(UPPER(TRIM(grid_mode)), '') IN ('LOSTCOM', 'OFF_GRID')
    """)

    records = df_to_update[
        [
            "site_id",
            "grid_date",
            "grid_mode",
            "grid_availability_pct",
            "grid_outages_per_day",
            "source",
            "status",
        ]
    ].to_dict(
        orient="records"
    )

    batch_size = 50
    pause_seconds = 5
    max_attempts = 3

    total_updated = 0

    for start in range(0, len(records), batch_size):

        end = min(start + batch_size, len(records))
        batch = records[start:end]

        success = False
        attempt = 1

        while not success and attempt <= max_attempts:

            try:
                with engine.begin() as conn:

                    conn.execute(
                        text("SET LOCAL statement_timeout = '10min';")
                    )

                    conn.execute(
                        update_sql,
                        batch
                    )

                success = True
                total_updated += len(batch)

                print(
                    f"✅ Batch mis à jour : {end}/{len(records)}"
                )

            except OperationalError as e:

                print(
                    f"⚠️ Erreur batch {start}-{end}, tentative {attempt}/{max_attempts}"
                )

                print(e)

                engine.dispose()
                time.sleep(30)

                attempt += 1

        if not success:
            raise RuntimeError(
                f"❌ Échec update batch {start}-{end}"
            )

        if end < len(records):
            time.sleep(pause_seconds)

    print(
        f"✅ Mise à jour terminée : {total_updated} lignes traitées."
    )

    print("✅ Mise à jour terminée.")
    print(f"Nombre de lignes mises à jour : {len(records)}")

    preview_file = REJECTED_DIR / "updated_grid_lostcom_offgrid_fms2_preview.xlsx"

    df_to_update[
        [
            "code_site",
            "grid_date",
            "old_grid_mode",
            "grid_mode",
            "grid_availability_pct",
            "grid_outages_per_day",
            "source",
            "status",
        ]
    ].to_excel(
        preview_file,
        index=False
    )

    print(f"📄 Fichier de contrôle créé : {preview_file}")


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    update_grid_lostcom_from_fms2(
        DEFAULT_FILE_PATH
    )