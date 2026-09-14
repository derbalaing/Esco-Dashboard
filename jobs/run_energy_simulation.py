import sys
import argparse
import importlib.util
from pathlib import Path

import pandas as pd
from sqlalchemy import text


# =====================================================
# PATH CONFIG
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SIMULATOR_ROOT = PROJECT_ROOT / "modules" / "EnergySimulator"
DATABASE_FILE = PROJECT_ROOT / "config" / "database.py"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(SIMULATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(SIMULATOR_ROOT))

if not DATABASE_FILE.exists():
    raise FileNotFoundError(
        f"Fichier database.py introuvable : {DATABASE_FILE}"
    )

spec = importlib.util.spec_from_file_location(
    "dailyanalyst_database",
    DATABASE_FILE
)

database_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database_module)

engine = database_module.engine


# =====================================================
# IMPORT MODELS
# =====================================================

from models.simulation_config import SimulationConfig
from models.solar import SolarModel
from models.grid import GridModel
from models.load import Load
from models.battery import Battery
from models.generator import Generator
from models.energy_manager import EnergyManager


# =====================================================
# HELPERS
# =====================================================

def f(value, default=0.0):
    try:
        if pd.isna(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def i(value, default=0):
    try:
        if pd.isna(value):
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def pick(summary, keys, default=0):
    for key in keys:
        if key in summary:
            return summary[key]
    return default


# =====================================================
# TABLE RESULTATS
# =====================================================

def create_energy_kpi_table():

    sql = text("""
    CREATE TABLE IF NOT EXISTS energy_kpi_daily
    (
        energy_kpi_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES sites(site_id),
        kpi_date DATE NOT NULL,

        load_energy_kwh NUMERIC(14,3) DEFAULT 0,
        solar_energy_kwh NUMERIC(14,3) DEFAULT 0,
        grid_energy_kwh NUMERIC(14,3) DEFAULT 0,
        battery_discharge_kwh NUMERIC(14,3) DEFAULT 0,
        generator_energy_kwh NUMERIC(14,3) DEFAULT 0,

        fuel_consumption_l NUMERIC(14,3) DEFAULT 0,
        generator_runtime_h NUMERIC(14,3) DEFAULT 0,
        generator_starts INTEGER DEFAULT 0,

        soc_min_pct NUMERIC(8,2),
        soc_final_pct NUMERIC(8,2),

        unserved_load_kwh NUMERIC(14,3) DEFAULT 0,

        load_source VARCHAR(50),
        solar_source VARCHAR(50),
        grid_source VARCHAR(50),

        simulation_hours INTEGER DEFAULT 24,
        dt_min INTEGER DEFAULT 5,

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        CONSTRAINT uq_energy_kpi_site_date UNIQUE (site_id, kpi_date)
    );
    """)

    index_sql = text("""
    CREATE INDEX IF NOT EXISTS idx_energy_kpi_site_date
    ON energy_kpi_daily(site_id, kpi_date);
    """)

    alter_sql = text("""
    ALTER TABLE energy_kpi_daily
    ADD COLUMN IF NOT EXISTS soc_start_pct NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS generator_initial_running BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS generator_final_running BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS initial_state_source VARCHAR(50),
    ADD COLUMN IF NOT EXISTS previous_kpi_date DATE;
    """)

    with engine.begin() as conn:
        conn.execute(sql)
        conn.execute(index_sql)
        conn.execute(alter_sql)
        


# =====================================================
# DATES A SIMULER
# =====================================================

def get_dates_to_simulate(date_debut=None, date_fin=None):

    conditions = [
        "simulation_ready_basic = TRUE"
    ]

    params = {}

    if date_debut is not None:
        conditions.append("load_date >= :date_debut")
        params["date_debut"] = date_debut

    if date_fin is not None:
        conditions.append("load_date <= :date_fin")
        params["date_fin"] = date_fin

    where_sql = " AND ".join(conditions)

    query = text(f"""
    SELECT DISTINCT
        load_date
    FROM v_site_simulation_inputs
    WHERE {where_sql}
    ORDER BY load_date
    """)

    df = pd.read_sql(
        query,
        engine,
        params=params
    )

    if df.empty:
        return []

    return [
        pd.to_datetime(x).date()
        for x in df["load_date"].tolist()
    ]




# =====================================================
# ETAT PRECEDENT J-1
# =====================================================

def get_previous_energy_state(site_id, current_date):
    """
    Récupère le dernier état connu avant la date simulée.
    SOC initial de J = SOC final de J-1.
    Etat GE initial de J = Etat GE final de J-1.
    """

    sql = text("""
        SELECT
            kpi_date,
            soc_final_pct,
            generator_final_running
        FROM energy_kpi_daily
        WHERE site_id = :site_id
          AND kpi_date < :current_date
        ORDER BY kpi_date DESC
        LIMIT 1
    """)

    with engine.begin() as conn:
        row = conn.execute(
            sql,
            {
                "site_id": int(site_id),
                "current_date": current_date,
            }
        ).mappings().first()

    if row is None:
        return None

    return dict(row)


# =====================================================
# BUILD MANAGER
# =====================================================

def build_manager(
    row,
    simulation_hours=24,
    dt=5,
    soc_start_pct=None,
    generator_initial_running=False
):

    config = SimulationConfig(
        simulation_hours=simulation_hours,
        dt=dt,
        ems_mode="reliability",
        generator_start_soc=f(row.get("soc_start_ge_pct"), 50),
        generator_stop_soc=f(row.get("soc_stop_ge_pct"), 95),
    )

    solar = SolarModel(
        daily_energy_kwh=f(row.get("daily_solar_kwh"), 0),
        dt=dt
    )

    grid = GridModel(
        availability=f(row.get("grid_availability_pct"), 0),
        outages=i(row.get("grid_outages_per_day"), 0),
        dt=dt
    )

    load = Load(
        mode="constant",
        average_power=f(row.get("avg_power_w"), 0),
        dt=dt
    )

    battery = Battery(
        battery_type=row.get("battery_type", "ACID"),
        nb_battery=i(row.get("nb_battery"), 1),
        capacity_ah=f(row.get("capacity_ah"), 100),
        nominal_voltage=f(row.get("battery_voltage_v"), 48),
        efficiency=f(row.get("battery_efficiency_pct"), 95),
        battery_quality=f(row.get("battery_quality_pct"), 100),
        dod=f(row.get("dod_pct"), 80),
        soc_initial=f(soc_start_pct, f(row.get("soc_initial_pct"), 80)),
        soc_start_charge=f(row.get("soc_start_charge_pct"), 50),
        soc_stop_charge=f(row.get("soc_stop_charge_pct"), 95),
        k1=f(row.get("k1"), 0.20),
        k2=f(row.get("k2"), 0.05),
        dt=dt,
        generator_start_soc=f(row.get("soc_start_ge_pct"), 50),
        generator_stop_soc=f(row.get("soc_stop_ge_pct"), 95),
    )

    fuel_curve = {
        25: f(row.get("fuel_25_lph"), 1.5),
        50: f(row.get("fuel_50_lph"), 3.0),
        75: f(row.get("fuel_75_lph"), 4.5),
        100: f(row.get("fuel_100_lph"), 6.0),
    }

    generator = Generator(
        rated_power_kw=f(row.get("generator_power_kw"), 0),
        fuel_curve=fuel_curve,
        dt=dt
    )

        # Etat initial GE venant de J-1
    for attr in ["is_running", "running", "is_on"]:
        if hasattr(generator, attr):
            setattr(generator, attr, bool(generator_initial_running))

    if hasattr(generator, "status"):
        generator.status = "RUNNING" if generator_initial_running else "OFF"

    manager = EnergyManager(
        solar=solar,
        grid=grid,
        load=load,
        battery=battery,
        generator=generator,
        config=config
    )

    return manager


# =====================================================
# SAVE RESULT
# =====================================================

def save_result(result):

    sql = text("""
    INSERT INTO energy_kpi_daily
    (
        site_id,
        kpi_date,

        load_energy_kwh,
        solar_energy_kwh,
        grid_energy_kwh,
        battery_discharge_kwh,
        generator_energy_kwh,

        fuel_consumption_l,
        generator_runtime_h,
        generator_starts,

        soc_min_pct,
        soc_final_pct,
        soc_start_pct,
        generator_initial_running,
        generator_final_running,
        initial_state_source,
        previous_kpi_date,

        unserved_load_kwh,

        load_source,
        solar_source,
        grid_source,

        simulation_hours,
        dt_min,

        updated_at
    )
    VALUES
    (
        :site_id,
        :kpi_date,

        :load_energy_kwh,
        :solar_energy_kwh,
        :grid_energy_kwh,
        :battery_discharge_kwh,
        :generator_energy_kwh,

        :fuel_consumption_l,
        :generator_runtime_h,
        :generator_starts,

        :soc_min_pct,
        :soc_final_pct,

        :soc_start_pct,
        :generator_initial_running,
        :generator_final_running,
        :initial_state_source,
        :previous_kpi_date,

        :unserved_load_kwh,

        :load_source,
        :solar_source,
        :grid_source,

        :simulation_hours,
        :dt_min,

        NOW()
    )
    ON CONFLICT (site_id, kpi_date)
    DO UPDATE SET

        load_energy_kwh = EXCLUDED.load_energy_kwh,
        solar_energy_kwh = EXCLUDED.solar_energy_kwh,
        grid_energy_kwh = EXCLUDED.grid_energy_kwh,
        battery_discharge_kwh = EXCLUDED.battery_discharge_kwh,
        generator_energy_kwh = EXCLUDED.generator_energy_kwh,

        fuel_consumption_l = EXCLUDED.fuel_consumption_l,
        generator_runtime_h = EXCLUDED.generator_runtime_h,
        generator_starts = EXCLUDED.generator_starts,

        soc_min_pct = EXCLUDED.soc_min_pct,
        soc_final_pct = EXCLUDED.soc_final_pct,

        
        soc_start_pct = EXCLUDED.soc_start_pct,
        generator_initial_running = EXCLUDED.generator_initial_running,
        generator_final_running = EXCLUDED.generator_final_running,
        initial_state_source = EXCLUDED.initial_state_source,
        previous_kpi_date = EXCLUDED.previous_kpi_date,

        unserved_load_kwh = EXCLUDED.unserved_load_kwh,

        load_source = EXCLUDED.load_source,
        solar_source = EXCLUDED.solar_source,
        grid_source = EXCLUDED.grid_source,

        simulation_hours = EXCLUDED.simulation_hours,
        dt_min = EXCLUDED.dt_min,

        updated_at = NOW();
    """)

    with engine.begin() as conn:
        conn.execute(sql, result)



def extract_generator_final_running(manager):
    """
    Récupère l'état final du GE après simulation.
    """

    generator = getattr(manager, "generator", None)

    if generator is None:
        return False

    for attr in ["is_running", "running", "is_on"]:
        if hasattr(generator, attr):
            return bool(getattr(generator, attr))

    if hasattr(generator, "status"):
        return str(generator.status).upper() in [
            "RUNNING",
            "ON",
            "STARTED",
        ]

    return False

# =====================================================
# SIMULER UNE LIGNE SITE/JOUR
# =====================================================

def simulate_row(row, simulation_hours=24, dt=5):

    current_date = pd.to_datetime(row["load_date"]).date()

    previous_state = get_previous_energy_state(
        site_id=row["site_id"],
        current_date=current_date
    )

    if (
        previous_state is not None
        and previous_state.get("soc_final_pct") is not None
    ):
        soc_start_pct = f(previous_state["soc_final_pct"], 80)
        generator_initial_running = bool(
            previous_state.get("generator_final_running", False)
        )
        initial_state_source = "PREVIOUS_DAY"
        previous_kpi_date = previous_state["kpi_date"]

    else:
        soc_start_pct = f(row.get("soc_initial_pct"), 80)
        generator_initial_running = False
        initial_state_source = "BATTERY_CONFIG"
        previous_kpi_date = None

    manager = build_manager(
        row=row,
        simulation_hours=simulation_hours,
        dt=dt,
        soc_start_pct=soc_start_pct,
        generator_initial_running=generator_initial_running
    )

    manager.run()

    summary = manager.summary()


    generator_final_running = extract_generator_final_running(manager)

    result = {
        "site_id": int(row["site_id"]),
        "kpi_date": pd.to_datetime(row["load_date"]).date(),
        "soc_start_pct": soc_start_pct,
        "generator_initial_running": generator_initial_running,
        "generator_final_running": generator_final_running,
        "initial_state_source": initial_state_source,
        "previous_kpi_date": previous_kpi_date,
        "load_energy_kwh": f(
            pick(
                summary,
                [
                    "Load Energy (kWh)",
                    "Load Energy kWh",
                    "load_energy_kwh",
                ],
                0
            )
        ),

        "solar_energy_kwh": f(
            pick(
                summary,
                [
                    "Solar Production (kWh)",
                    "Solar Energy (kWh)",
                    "solar_energy_kwh",
                ],
                0
            )
        ),

        "grid_energy_kwh": f(
            pick(
                summary,
                [
                    "Grid Energy (kWh)",
                    "grid_energy_kwh",
                ],
                0
            )
        ),

        "battery_discharge_kwh": f(
            pick(
                summary,
                [
                    "Battery Discharge (kWh)",
                    "Battery Energy (kWh)",
                    "battery_discharge_kwh",
                ],
                0
            )
        ),

        "generator_energy_kwh": f(
            pick(
                summary,
                [
                    "Generator Energy (kWh)",
                    "GE Energy (kWh)",
                    "generator_energy_kwh",
                ],
                0
            )
        ),

        "fuel_consumption_l": f(
            pick(
                summary,
                [
                    "Fuel Consumption (L)",
                    "Fuel Consumption L",
                    "fuel_consumption_l",
                ],
                0
            )
        ),

        "generator_runtime_h": f(
            pick(
                summary,
                [
                    "Generator Running Hours",
                    "Generator Runtime (h)",
                    "generator_runtime_h",
                ],
                0
            )
        ),

        "generator_starts": i(
            pick(
                summary,
                [
                    "Generator Starts",
                    "generator_starts",
                ],
                0
            )
        ),

        "soc_min_pct": f(
            pick(
                summary,
                [
                    "SOC Min (%)",
                    "soc_min_pct",
                ],
                0
            )
        ),

        "soc_final_pct": f(
            pick(
                summary,
                [
                    "SOC Final (%)",
                    "Final SOC (%)",
                    "soc_final_pct",
                ],
                0
            )
        ),

        "unserved_load_kwh": f(
            pick(
                summary,
                [
                    "Unserved Load (kWh)",
                    "unserved_load_kwh",
                ],
                0
            )
        ),

        "load_source": row.get("load_source", None),
        "solar_source": row.get("solar_source", None),
        "grid_source": row.get("grid_source", None),

        "simulation_hours": simulation_hours,
        "dt_min": dt,
    }

    return result


# =====================================================
# RUN SIMULATION
# =====================================================

def run_energy_simulation(
    load_date=None,
    date_debut=None,
    date_fin=None,
    simulation_hours=24,
    dt=5,
    limit=None
):

    create_energy_kpi_table()

    if load_date is not None:

        dates = [
            pd.to_datetime(load_date).date()
        ]

    else:

        dates = get_dates_to_simulate(
            date_debut=date_debut,
            date_fin=date_fin
        )

    if len(dates) == 0:
        print("⚠️ Aucune date prête pour simulation.")
        return

    total_saved = 0

    for current_date in dates:

        print("")
        print("=" * 80)
        print(f"📅 Simulation date : {current_date}")
        print("=" * 80)

        query_sql = """
        SELECT *
        FROM v_site_simulation_inputs
        WHERE load_date = :load_date
          AND simulation_ready_basic = TRUE
        ORDER BY code_site
        """
        alter_sql = text("""
        ALTER TABLE energy_kpi_daily
        ADD COLUMN IF NOT EXISTS soc_start_pct NUMERIC(8,2),
        ADD COLUMN IF NOT EXISTS generator_initial_running BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS generator_final_running BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS initial_state_source VARCHAR(50),
        ADD COLUMN IF NOT EXISTS previous_kpi_date DATE;
        """)

        if limit is not None:
            query_sql += f" LIMIT {int(limit)}"

        df = pd.read_sql(
            text(query_sql),
            engine,
            params={
                "load_date": current_date
            }
        )

        if df.empty:
            print(f"⚠️ Aucun site prêt pour la date {current_date}")
            continue

        print(f"Nombre de sites à simuler : {len(df)}")

        for _, row in df.iterrows():

            try:

                result = simulate_row(
                    row=row,
                    simulation_hours=simulation_hours,
                    dt=dt
                )

                save_result(result)

                total_saved += 1

                print(
                    f"✅ {row['code_site']} | "
                    f"Load={result['load_energy_kwh']:.2f} kWh | "
                    f"Solar={result['solar_energy_kwh']:.2f} kWh | "
                    f"Grid={result['grid_energy_kwh']:.2f} kWh | "
                    f"GE={result['generator_runtime_h']:.2f} h | "
                    f"Fuel={result['fuel_consumption_l']:.2f} L | "
                    f"SOCf={result['soc_final_pct']:.1f}%"
                )

            except Exception as e:

                print(
                    f"❌ Erreur site {row.get('code_site')} "
                    f"date {current_date} : {e}"
                )

    print("")
    print("=" * 80)
    print(f"✅ Simulation terminée. Lignes sauvegardées : {total_saved}")
    print("=" * 80)


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Simulation énergétique par site et par jour"
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date unique à simuler. Exemple : 2026-07-28"
    )

    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Date début. Exemple : 2026-07-01"
    )

    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Date fin. Exemple : 2026-07-31"
    )

    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Durée simulation en heures. Défaut = 24"
    )

    parser.add_argument(
        "--dt",
        type=int,
        default=5,
        help="Pas de simulation en minutes. Défaut = 5"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limiter le nombre de sites par jour pour test"
    )

    args = parser.parse_args()

    run_energy_simulation(
        load_date=args.date,
        date_debut=args.start,
        date_fin=args.end,
        simulation_hours=args.hours,
        dt=args.dt,
        limit=args.limit
    )





    