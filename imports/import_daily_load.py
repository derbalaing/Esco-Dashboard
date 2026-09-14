import pandas as pd
from sqlalchemy import text
from pathlib import Path
import re
from datetime import datetime, date
import pandas as pd
import time
from sqlalchemy.exc import OperationalError


import sys
import os

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from config.database import engine




def parse_excel_date(value):
    """
    Lecture robuste des dates Excel.

    Cas supportés :
    - 2026-07-01      => 1 juillet 2026
    - 01/07/2026      => 1 juillet 2026
    - 01-07-2026      => 1 juillet 2026
    - Timestamp Excel => date correcte
    """

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.date()

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    # Cas Excel serial number
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

    # Garder uniquement la partie date si format avec heure
    s10 = s[:10]

    # Format ISO : 2026-07-01 ou 2026/07/01
    # Ici il ne faut PAS utiliser dayfirst=True
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

    # Format français : 01/07/2026 ou 01-07-2026
    if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$", s10):
        dt = pd.to_datetime(
            s10,
            dayfirst=True,
            errors="coerce"
        )

        if pd.isna(dt):
            return None

        return dt.date()

    # Fallback
    dt = pd.to_datetime(
        s,
        errors="coerce"
    )

    if pd.isna(dt):
        return None

    return dt.date()
# =====================================================
# PARAMETRES FICHIER EXCEL
# =====================================================

# A adapter seulement si le code site n'est pas détecté automatiquement.
# Exemple : "A", "B", "C"...
CODE_SITE_COL_LETTER = "C"

DATE_COL_LETTER = "I"
MANUAL_COL_LETTER = "J"
FMS_AC_COL_LETTER = "K"
FMS_DC_COL_LETTER = "Y"

MIN_VALID_POWER_W = 200


# =====================================================
# OUTILS
# =====================================================

def excel_col_to_index(col_letter):
    """
    Convertit une colonne Excel en index pandas.
    Exemple :
        A -> 0
        I -> 8
        Y -> 24
    """

    col_letter = col_letter.upper().strip()

    index = 0

    for char in col_letter:
        index = index * 26 + (ord(char) - ord("A") + 1)

    return index - 1


def to_number(value):
    """
    Convertit une valeur Excel en float.
    Accepte :
        2600
        -2600
        "2 600"
        "2,600"
        "2600 W"
    """

    if pd.isna(value):
        return None

    value = str(value)
    value = value.replace("W", "")
    value = value.replace("w", "")
    value = value.replace(" ", "")
    value = value.replace(",", ".")
    value = value.strip()

    try:
        return float(value)

    except Exception:
        return None


def get_column_by_letter(df, letter):
    idx = excel_col_to_index(letter)

    if idx >= len(df.columns):
        raise ValueError(
            f"La colonne {letter} n'existe pas dans le fichier Excel."
        )

    return df.iloc[:, idx]


def detect_code_site_column(df):
    """
    Essaie de trouver automatiquement la colonne code site.
    Sinon utilise CODE_SITE_COL_LETTER.
    """

    possible_names = [
        "code_site",
        "site_code",
        "code site",
        "site",
        "sites",
        "code",
    ]

    normalized_columns = {
        str(col).strip().lower().replace("-", "_"): col
        for col in df.columns
    }

    for name in possible_names:
        key = name.strip().lower().replace("-", "_")

        if key in normalized_columns:
            return df[normalized_columns[key]]

    return get_column_by_letter(
        df,
        CODE_SITE_COL_LETTER
    )


def choose_load(row):
    """
    Applique la logique demandée :

    1. Colonne Y si abs(Y) > 200 W => FMS-DC
    2. Colonne K si abs(K) > 200 W => FMS-AC
    3. Sinon colonne J => Manual
    4. Sinon 0 => No Data
    """

    fms_dc = row["fms_dc_power_w"]
    fms_ac = row["fms_ac_power_w"]
    manual = row["manual_power_w"]

    if fms_dc is not None and abs(fms_dc) > MIN_VALID_POWER_W:
        return abs(fms_dc), "FMS-DC"

    if fms_ac is not None and abs(fms_ac) > MIN_VALID_POWER_W:
        return abs(fms_ac), "FMS-AC"

    if manual is not None:
        manual_value = abs(manual)

        if manual_value > 0:
            return manual_value, "Manual"

    return 0, "No Data"


# =====================================================
# CREATE TABLE
# =====================================================

def create_site_daily_load_table():

    sql = text("""
    CREATE TABLE IF NOT EXISTS site_daily_load
    (
        load_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES sites(site_id),

        load_date DATE NOT NULL,

        avg_power_w NUMERIC(12,2) NOT NULL DEFAULT 0,

        source VARCHAR(30) DEFAULT 'No Data',

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        CONSTRAINT uq_site_daily_load UNIQUE (site_id, load_date)
    );
    """)

    index_sql = text("""
    CREATE INDEX IF NOT EXISTS idx_site_daily_load_site_date
    ON site_daily_load(site_id, load_date);
    """)

    with engine.begin() as conn:
        conn.execute(sql)

        # On évite de bloquer l'import si l'index prend trop de temps
        print("✅ Table site_daily_load vérifiée/créée.")


# =====================================================
# IMPORT EXCEL
# =====================================================

def import_daily_load_excel(file_path="data/Load_Daily.xlsx"):

    create_site_daily_load_table()

    df_raw = pd.read_excel(file_path)

    if df_raw.empty:
        raise ValueError("Le fichier Excel est vide.")

    # =====================================================
    # EXTRACTION DES COLONNES
    # =====================================================

    df = pd.DataFrame()

    df["code_site"] = detect_code_site_column(df_raw)

    df["load_date"] = get_column_by_letter(
        df_raw,
        DATE_COL_LETTER
    )

    df["manual_power_w"] = get_column_by_letter(
        df_raw,
        MANUAL_COL_LETTER
    )

    df["fms_ac_power_w"] = get_column_by_letter(
        df_raw,
        FMS_AC_COL_LETTER
    )

    df["fms_dc_power_w"] = get_column_by_letter(
        df_raw,
        FMS_DC_COL_LETTER
    )

    # =====================================================
    # NETTOYAGE
    # =====================================================

    df["code_site"] = (
        df["code_site"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["load_date"] = df["load_date"].apply(parse_excel_date)

    for col in [
        "manual_power_w",
        "fms_ac_power_w",
        "fms_dc_power_w",
    ]:
        df[col] = df[col].apply(to_number)

    # Supprimer les lignes sans site ou sans date
    df = df[
        (df["code_site"].notna())
        &
        (df["code_site"] != "")
        &
        (df["code_site"] != "NAN")
        &
        (df["load_date"].notna())
    ].copy()

    if df.empty:
        raise ValueError(
            "Aucune ligne valide trouvée après nettoyage code_site/date."
        )

    # =====================================================
    # APPLICATION LOGIQUE LOAD
    # =====================================================

    results = df.apply(
        choose_load,
        axis=1,
        result_type="expand"
    )

    df["avg_power_w"] = results[0]
    df["source"] = results[1]

    # =====================================================
    # RECUPERATION site_id
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

   # =====================================================
# GESTION DES SITES ABSENTS DE LA TABLE sites
# =====================================================

    missing_sites = df[df["site_id"].isna()].copy()

    if not missing_sites.empty:

        rejected_dir = Path("data/rejected")
        rejected_dir.mkdir(parents=True, exist_ok=True)

        rejected_file = rejected_dir / "missing_sites_load.xlsx"

        missing_sites[
            [
                "code_site",
                "load_date",
                "avg_power_w",
                "source",
                "manual_power_w",
                "fms_ac_power_w",
                "fms_dc_power_w",
            ]
        ].to_excel(
            rejected_file,
            index=False
        )

        print("⚠️ Sites non trouvés dans la table sites :")
        print(
            ", ".join(
                missing_sites["code_site"]
                .astype(str)
                .unique()
            )
        )

        print(f"📄 Fichier des sites rejetés créé : {rejected_file}")

    # Garder uniquement les sites connus
    df = df[df["site_id"].notna()].copy()

    print("Nombre de lignes après exclusion des sites inconnus :", len(df))

    if df.empty:
        print("❌ Aucun site du fichier Load_Daily.xlsx n'existe dans la table sites.")
        print("➡️ Vérifiez les codes sites ou utilisez une table d'alias.")
        return {
            "rows_imported": 0,
            "sites_imported": 0,
            "summary": None,
        }

    df["site_id"] = df["site_id"].astype(int)

    # =====================================================
    # GESTION DES DOUBLONS SITE / DATE
    # =====================================================
    # Priorité :
    # FMS-DC > FMS-AC > Manual > No Data

    priority = {
        "FMS-DC": 1,
        "FMS-AC": 2,
        "Manual": 3,
        "No Data": 4,
    }

    df["source_priority"] = df["source"].map(priority).fillna(99)

    df = df.sort_values(
        by=[
            "site_id",
            "load_date",
            "source_priority",
        ]
    )

    df = df.drop_duplicates(
        subset=[
            "site_id",
            "load_date",
        ],
        keep="first"
    )

    # =====================================================
    # INSERT / UPDATE
    # =====================================================

    insert_sql = text("""
    INSERT INTO site_daily_load
    (
        site_id,
        load_date,
        avg_power_w,
        source,
        updated_at
    )
    VALUES
    (
        :site_id,
        :load_date,
        :avg_power_w,
        :source,
        NOW()
    )
    ON CONFLICT (site_id, load_date)
    DO UPDATE SET
        avg_power_w = EXCLUDED.avg_power_w,
        source = EXCLUDED.source,
        updated_at = NOW();
    """)

    # =====================================================
    # CREATION DES RECORDS
    # =====================================================

    records = df[
        [
            "site_id",
            "load_date",
            "avg_power_w",
            "source",
        ]
    ].to_dict(orient="records")

    # =====================================================
    # INSERTION PAR BATCH
    # =====================================================

    if len(records) == 0:
        print("❌ Aucun enregistrement à importer.")
        return {
            "rows_imported": 0,
            "sites_imported": 0,
            "summary": None,
        }

    batch_size = 100

    for start in range(0, len(records), batch_size):

        end = min(
            start + batch_size,
            len(records)
        )

        batch = records[start:end]

        with engine.begin() as conn:
            conn.execute(
                insert_sql,
                batch
            )

        print(
            f"✅ Batch Load Daily importé : {end}/{len(records)}"
        )

        # Pause entre les batchs, sauf après le dernier batch
        if end < len(records):
            print("⏳ Pause 30 secondes avant le prochain batch...")
            time.sleep(30)

    # =====================================================
    # SUMMARY
    # =====================================================

    summary = (
        df.groupby("source")
        .size()
        .reset_index(name="count")
        .sort_values("source")
    )

    print("✅ Import Load Daily terminé")
    print("Lignes importées :", len(records))
    print("Sites importés :", df["code_site"].nunique())
    print("")
    print(summary)

    return {
        "rows_imported": len(records),
        "sites_imported": df["code_site"].nunique(),
        "summary": summary,
    }

# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    import_daily_load_excel(
        "data/Load_Daily.xlsx"
    )


    