import sys
import os
import re
import time
from pathlib import Path
from datetime import datetime, date


import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from config.database import engine


# =====================================================
# PARAMETRES FICHIER
# =====================================================

CODE_SITE_COL_LETTER = "C"
GRID_DATE_COL_LETTER = "I"

GRID_VISIBILITY_AC_COL_LETTER = "AC"
GRID_VISIBILITY_AD_COL_LETTER = "AD"
GRID_AVAILABILITY_COL_LETTER = "AG"
GRID_OUTAGES_COL_LETTER = "AH"
GRID_VISIBILITY_MIN_FOR_OFFGRID = 60
DEFAULT_FILE_PATH = "data/Grid.xlsx"


# =====================================================
# OUTILS
# =====================================================

def parse_excel_date(value):
    """
    Lecture robuste des dates Excel.

    2026-07-01 => 1 juillet 2026
    01/07/2026 => 1 juillet 2026
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


def excel_col_to_index(col_letter):

    col_letter = str(col_letter).upper().strip()

    index = 0

    for char in col_letter:
        index = index * 26 + ord(char) - ord("A") + 1

    return index - 1


def get_column_by_letter(df, col_letter):

    idx = excel_col_to_index(col_letter)

    if idx >= len(df.columns):
        raise ValueError(
            f"La colonne {col_letter} n'existe pas dans le fichier Excel. "
            f"Nombre de colonnes détectées : {len(df.columns)}"
        )

    return df.iloc[:, idx]


def to_number(value):

    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip()

    if value == "" or value.upper() in ["NAN", "NONE", "NULL", "-"]:
        return None

    value = value.replace("%", "")
    value = value.replace(" ", "")
    value = value.replace(",", ".")

    try:
        return float(value)

    except Exception:
        return None


def normalize_availability(value):

    number = to_number(value)

    if number is None:
        return None

    if pd.isna(number):
        return None

    # Si Excel donne 0.95 au lieu de 95 %
    if 0 <= number <= 1:
        number = number * 100

    if number < 0:
        number = 0

    if number > 100:
        number = 100

    return round(float(number), 2)


def to_int_or_none(value):

    number = to_number(value)

    if number is None:
        return None

    if pd.isna(number):
        return None

    if number < 0:
        return 0

    return int(round(float(number)))

def is_ni_nc(value):

    if value is None:
        return False

    try:
        if pd.isna(value):
            return False
    except Exception:
        pass

    value = str(value).strip().upper()

    return value in [
        "NI",
        "NC",
        "N/I",
        "N/C",
    ]


def compute_grid_status(row):

    visibility = row.get("grid_visibility_pct")
    availability = row.get("grid_availability_pct")
    outages_from_file = row.get("grid_outages_from_file")

    availability_raw = row.get("grid_availability_raw")
    outages_raw = row.get("grid_outages_raw")

    if pd.isna(visibility):
        visibility = None

    if pd.isna(availability):
        availability = None

    if pd.isna(outages_from_file):
        outages_from_file = None

    # =====================================================
    # CAS 1 : LOSTCOM
    # AD = 0 ou vide
    # =====================================================

    if visibility is None or visibility <= 0:

        return pd.Series(
            {
                "grid_mode": "LOSTCOM",
                "grid_availability_pct": None,
                "grid_outages_per_day": None,
                "source": "FMS",
                "status": "LOSTCOM",
            }
        )

    # =====================================================
    # CAS 2 : OFF_GRID
    # AD >= 60 ET AG = 0
    # =====================================================

    if availability is not None:
        if visibility >= GRID_VISIBILITY_MIN_FOR_OFFGRID and availability <= 0:

            return pd.Series(
                {
                    "grid_mode": "OFF_GRID",
                    "grid_availability_pct": 0,
                    "grid_outages_per_day": 0,
                    "source": "FMS",
                    "status": "ACTIVE",
                }
            )

    # =====================================================
    # CAS 3 : OFF_GRID
    # AD >= 60 ET AG/AH = NI ou NC
    # =====================================================

    if visibility >= GRID_VISIBILITY_MIN_FOR_OFFGRID:
        if is_ni_nc(availability_raw) or is_ni_nc(outages_raw):

            return pd.Series(
                {
                    "grid_mode": "OFF_GRID",
                    "grid_availability_pct": 0,
                    "grid_outages_per_day": 0,
                    "source": "FMS",
                    "status": "ACTIVE",
                }
            )

    # =====================================================
    # CAS 4 : site visible mais disponibilité non lisible
    # =====================================================

    if availability is None:

        return pd.Series(
            {
                "grid_mode": "LOSTCOM",
                "grid_availability_pct": None,
                "grid_outages_per_day": None,
                "source": "FMS",
                "status": "LOSTCOM",
            }
        )

    # =====================================================
    # CAS 5 : ON_GRID disponibilité 100 %
    # =====================================================

    if availability >= 100:

        return pd.Series(
            {
                "grid_mode": "ON_GRID",
                "grid_availability_pct": 100,
                "grid_outages_per_day": 0,
                "source": "FMS",
                "status": "ACTIVE",
            }
        )

    # =====================================================
    # CAS 6 : ON_GRID disponibilité partielle
    # AH = nombre de coupures
    # =====================================================

    if outages_from_file is None:
        outages_from_file = 0

    return pd.Series(
        {
            "grid_mode": "ON_GRID",
            "grid_availability_pct": availability,
            "grid_outages_per_day": int(outages_from_file),
            "source": "FMS",
            "status": "ACTIVE",
        }
    )

    visibility = row.get("grid_visibility_pct")
    availability = row.get("grid_availability_pct")
    outages_from_file = row.get("grid_outages_from_file")

    if pd.isna(visibility):
        visibility = None

    if pd.isna(availability):
        availability = None

    if pd.isna(outages_from_file):
        outages_from_file = None

    # =====================================================
    # CAS 1 : LOSTCOM
    # AD = 0 ou vide
    # =====================================================

    if visibility is None or visibility <= 0:

        return pd.Series(
            {
                "grid_mode": "LOSTCOM",
                "grid_availability_pct": None,
                "grid_outages_per_day": None,
                "source": "FMS",
                "status": "LOSTCOM",
            }
        )

    # =====================================================
    # CAS 2 : site visible mais disponibilité AG non lisible
    # =====================================================

    if availability is None:

        return pd.Series(
            {
                "grid_mode": "LOSTCOM",
                "grid_availability_pct": None,
                "grid_outages_per_day": None,
                "source": "FMS",
                "status": "LOSTCOM",
            }
        )

    # =====================================================
    # CAS 3 : OFF_GRID
    # AD >= 60 ET disponibilité Grid = 0
    # =====================================================

    if visibility >= GRID_VISIBILITY_MIN_FOR_OFFGRID and availability <= 0:

        return pd.Series(
            {
                "grid_mode": "OFF_GRID",
                "grid_availability_pct": 0,
                "grid_outages_per_day": 0,
                "source": "FMS",
                "status": "ACTIVE",
            }
        )

    # =====================================================
    # CAS 4 : ON_GRID disponibilité 100 %
    # =====================================================

    if availability >= 100:

        return pd.Series(
            {
                "grid_mode": "ON_GRID",
                "grid_availability_pct": 100,
                "grid_outages_per_day": 0,
                "source": "FMS",
                "status": "ACTIVE",
            }
        )

    # =====================================================
    # CAS 5 : ON_GRID disponibilité partielle
    # AH = nombre de coupures
    # =====================================================

    if outages_from_file is None:
        outages_from_file = 0

    return pd.Series(
        {
            "grid_mode": "ON_GRID",
            "grid_availability_pct": availability,
            "grid_outages_per_day": int(outages_from_file),
            "source": "FMS",
            "status": "ACTIVE",
        }
    )

# =====================================================
# CREATE TABLE
# =====================================================

def create_grid_table():

    sql = text("""
    CREATE TABLE IF NOT EXISTS site_grid
    (
        grid_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES sites(site_id),

        grid_date DATE NOT NULL,

        grid_mode VARCHAR(30) DEFAULT 'ON_GRID',

        grid_availability_pct NUMERIC(5,2),

        grid_outages_per_day INTEGER,

        status VARCHAR(30) DEFAULT 'ACTIVE',

        source VARCHAR(50) DEFAULT 'MANUAL',

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        CONSTRAINT uq_site_grid_date UNIQUE (site_id, grid_date)
    );
    """)

    check_index_sql = text("""
    SELECT COUNT(*) AS index_exists
    FROM pg_indexes
    WHERE tablename = 'site_grid'
      AND indexname = 'idx_site_grid_site_date';
    """)

    create_index_sql = text("""
    CREATE INDEX idx_site_grid_site_date
    ON site_grid(site_id, grid_date);
    """)

    with engine.begin() as conn:

        conn.execute(sql)

        index_exists = conn.execute(
            check_index_sql
        ).scalar()

        if index_exists == 0:

            conn.execute(
                text("SET LOCAL statement_timeout = '10min';")
            )

            conn.execute(create_index_sql)

            print("✅ Index site_grid créé.")

        else:

            print("✅ Index site_grid déjà existant.")


# =====================================================
# IMPORT GRID
# =====================================================

def import_grid_excel(file_path=DEFAULT_FILE_PATH):

    create_grid_table()

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {file_path}"
        )

    df_raw = pd.read_excel(
        file_path,
        header=None
    )

    if df_raw.empty:
        raise ValueError("Le fichier Excel est vide.")

    print(
        f"Fichier Grid lu : {file_path} | "
        f"{df_raw.shape[0]} lignes x {df_raw.shape[1]} colonnes"
    )

    df = pd.DataFrame()

    # =====================================================
    # LECTURE COLONNES
    # =====================================================

    df["code_site"] = get_column_by_letter(
        df_raw,
        CODE_SITE_COL_LETTER
    )

    df["grid_date"] = get_column_by_letter(
        df_raw,
        GRID_DATE_COL_LETTER
    )

    df["grid_visibility_ac_raw"] = get_column_by_letter(
        df_raw,
        GRID_VISIBILITY_AC_COL_LETTER
    )

    df["grid_visibility_ad_raw"] = get_column_by_letter(
        df_raw,
        GRID_VISIBILITY_AD_COL_LETTER
)

    df["grid_availability_raw"] = get_column_by_letter(
        df_raw,
        GRID_AVAILABILITY_COL_LETTER
    )

    df["grid_outages_raw"] = get_column_by_letter(
        df_raw,
        GRID_OUTAGES_COL_LETTER
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

    df["grid_date"] = df["grid_date"].apply(
        parse_excel_date
    )

    df["grid_visibility_ac_pct"] = df["grid_visibility_ac_raw"].apply(
        normalize_availability
    )

    df["grid_visibility_ad_pct"] = df["grid_visibility_ad_raw"].apply(
        normalize_availability
    )


    def max_visibility(row):

        values = []

        ac = row.get("grid_visibility_ac_pct")
        ad = row.get("grid_visibility_ad_pct")

        if ac is not None and not pd.isna(ac):
            values.append(ac)

        if ad is not None and not pd.isna(ad):
            values.append(ad)

        if not values:
            return None

        return max(values)


    df["grid_visibility_pct"] = df.apply(
        max_visibility,
        axis=1
    )

    df["grid_availability_pct"] = df["grid_availability_raw"].apply(
        normalize_availability
    )

    df["grid_outages_from_file"] = df["grid_outages_raw"].apply(
        to_int_or_none
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
        raise ValueError("Aucune ligne valide trouvée après nettoyage.")

    # =====================================================
    # LOGIQUE GRID
    # =====================================================

    df[
        [
            "grid_mode",
            "grid_availability_pct",
            "grid_outages_per_day",
            "source",
            "status",
        ]
    ] = df.apply(
        compute_grid_status,
        axis=1
    )


    df[
        [
            "grid_mode",
            "grid_availability_pct",
            "grid_outages_per_day",
            "source",
            "status",
        ]
    ] = df.apply(
        compute_grid_status,
        axis=1
    )


# =====================================================
# CONTROLE OFF_GRID
# =====================================================

    df_offgrid_expected = df[
        (df["grid_visibility_pct"] >= GRID_VISIBILITY_MIN_FOR_OFFGRID)
        &
        (df["grid_availability_pct"] == 0)
    ].copy()

    df_offgrid_wrong = df_offgrid_expected[
        df_offgrid_expected["grid_mode"] != "OFF_GRID"
    ].copy()

    if not df_offgrid_wrong.empty:

        rejected_dir = Path("data/rejected")
        rejected_dir.mkdir(parents=True, exist_ok=True)

        debug_file = rejected_dir / "wrong_offgrid_detection.xlsx"

        df_offgrid_wrong[
            [
                "code_site",
                "grid_date",
                "grid_visibility_ac_raw",
                "grid_visibility_ad_raw",
                "grid_availability_raw",
                "grid_outages_raw",
                "grid_visibility_ac_pct",
                "grid_visibility_ad_pct",
                "grid_visibility_pct",
                "grid_availability_pct",
                "grid_mode",
                "status",
            ]
        ].to_excel(
            debug_file,
            index=False
        )

        print("❌ Attention : des sites AC ou AD >= 60 et disponibilité=0 ne sont pas OFF_GRID")
        print(f"📄 Fichier contrôle créé : {debug_file}")

    else:

        print(
            f"✅ Contrôle OFF_GRID OK : "
            f"{len(df_offgrid_expected)} sites détectés OFF_GRID"
        )




    # =====================================================
    # RECUPERATION SITE_ID
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

        rejected_dir = Path("data/rejected")
        rejected_dir.mkdir(parents=True, exist_ok=True)

        rejected_file = rejected_dir / "missing_sites_grid.xlsx"

        missing_sites[
            [
                "code_site",
                "grid_date",
                "grid_visibility_ac_raw",
                "grid_visibility_ad_raw",
                "grid_availability_raw",
                "grid_outages_raw",
                "grid_visibility_ac_pct",
                "grid_visibility_ad_pct",
                "grid_visibility_pct",
                "grid_availability_pct",
                "grid_outages_from_file",
                "grid_mode",
                "status",
            ]
        ].to_excel(
            rejected_file,
            index=False
        )

        print("⚠️ Sites Grid non trouvés dans la table sites :")
        print(
            ", ".join(
                sorted(
                    missing_sites["code_site"]
                    .astype(str)
                    .unique()
                )
            )
        )

        print(
            f"📄 Fichier des sites rejetés créé : {rejected_file}"
        )

    df = df[
        df["site_id"].notna()
    ].copy()

    if df.empty:
        print("❌ Aucun site Grid importable.")
        return

    df["site_id"] = df["site_id"].astype(int)

    # =====================================================
    # GESTION DOUBLONS
    # =====================================================
    # Pour un même site + date :
    # priorité ACTIVE avant LOSTCOM
    # =====================================================

    df["status_priority"] = df["status"].map(
        {
            "ACTIVE": 1,
            "LOSTCOM": 2,
        }
    ).fillna(99)

    df = df.sort_values(
        by=[
            "site_id",
            "grid_date",
            "status_priority",
        ]
    )

    df = df.drop_duplicates(
        subset=[
            "site_id",
            "grid_date",
        ],
        keep="first"
    )

    df = df.where(
        pd.notnull(df),
        None
    )

    # =====================================================
    # INSERT / UPDATE
    # =====================================================

    insert_sql = text("""
    INSERT INTO site_grid
    (
        site_id,
        grid_date,
        grid_mode,
        grid_availability_pct,
        grid_outages_per_day,
        source,
        status,
        updated_at
    )
    VALUES
    (
        :site_id,
        :grid_date,
        :grid_mode,
        :grid_availability_pct,
        :grid_outages_per_day,
        :source,
        :status,
        NOW()
    )
    ON CONFLICT (site_id, grid_date)
    DO UPDATE SET
        grid_mode = EXCLUDED.grid_mode,
        grid_availability_pct = EXCLUDED.grid_availability_pct,
        grid_outages_per_day = EXCLUDED.grid_outages_per_day,
        source = EXCLUDED.source,
        status = EXCLUDED.status,
        updated_at = NOW();
    """)

    # =====================================================
    # NETTOYAGE FINAL AVANT INSERT
    # =====================================================

    def clean_float_or_none(value):

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        try:
            return float(value)
        except Exception:
            return None


    def clean_int_or_none(value):

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        try:
            return int(round(float(value)))
        except Exception:
            return None


    records = []

    for _, r in df.iterrows():

        records.append(
            {
                "site_id": int(r["site_id"]),
                "grid_date": r["grid_date"],
                "grid_mode": r["grid_mode"],
                "grid_availability_pct": clean_float_or_none(
                    r["grid_availability_pct"]
                ),
                "grid_outages_per_day": clean_int_or_none(
                    r["grid_outages_per_day"]
                ),
                "source": r["source"],
                "status": r["status"],
            }
        )

        batch_size = 200

    print(f"Début import Grid : {len(records)} lignes...")

    for start in range(0, len(records), batch_size):

        end = min(
            start + batch_size,
            len(records)
        )

        batch = records[start:end]

        success = False
        attempt = 1
        max_attempts = 3

        while not success and attempt <= max_attempts:

            try:
                with engine.begin() as conn:
                    conn.execute(
                        insert_sql,
                        batch
                    )

                success = True

                print(
                    f"✅ Batch Grid importé : {end}/{len(records)}"
                )

            except OperationalError as e:

                print("")
                print(
                    f"⚠️ Connexion PostgreSQL coupée sur le batch "
                    f"{start + 1}-{end}"
                )
                print(f"Tentative {attempt}/{max_attempts}")
                print("⏳ Pause 60 secondes avant retry...")

                engine.dispose()
                time.sleep(30)

                attempt += 1

        if not success:
            raise RuntimeError(
                f"❌ Echec import Grid après {max_attempts} tentatives "
                f"sur le batch {start + 1}-{end}"
            )

        # Pause entre les batchs, sauf après le dernier batch
        if end < len(records):
            print("⏳ Pause 60 secondes avant le prochain batch...")
            time.sleep(60)


    df_insert = df[
        [
            "site_id",
            "grid_date",
            "grid_mode",
            "grid_availability_pct",
            "grid_outages_per_day",
            "source",
            "status",
        ]
    ].copy()


    def clean_value(value):

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        return value

# =====================================================
# NETTOYAGE FINAL AVANT INSERT
# =====================================================

def clean_float_or_none(value):

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return float(value)
    except Exception:
        return None


    def clean_int_or_none(value):

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        try:
            return int(round(float(value)))
        except Exception:
            return None


    df_insert["site_id"] = df_insert["site_id"].apply(
        lambda x: int(x)
    )

    df_insert["grid_availability_pct"] = df_insert["grid_availability_pct"].apply(
        clean_float_or_none
    )

    df_insert["grid_outages_per_day"] = df_insert["grid_outages_per_day"].apply(
        clean_int_or_none
    )

    # Très important : forcer les colonnes en object pour garder None au lieu de NaN
    df_insert = df_insert.astype(object)

    df_insert = df_insert.where(
        pd.notnull(df_insert),
        None
    )

    records = df_insert.to_dict(
        orient="records"
    )


    print(f"Début import Grid : {len(records)} lignes...")

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
            f"✅ Batch Grid importé : {end}/{len(records)}"
        )

    print("")
    print("✅ Import Grid terminé")
    print("Lignes importées :", len(records))
    print("Sites importés :", df["code_site"].nunique())

    summary = (
        df.groupby(
            [
                "grid_mode",
                "status",
            ]
        )
        .size()
        .reset_index(name="count")
        .sort_values(
            [
                "grid_mode",
                "status",
            ]
        )
    )

    print("")
    print(summary)


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    import_grid_excel(
        DEFAULT_FILE_PATH
    )