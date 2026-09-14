import sys
from pathlib import Path
from datetime import timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text

from config.database import engine


# =====================================================
# PATH ENERGY SIMULATOR
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_ROOT = PROJECT_ROOT / "modules" / "EnergySimulator"

if str(SIMULATOR_ROOT) not in sys.path:
    sys.path.append(str(SIMULATOR_ROOT))


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


def kpi_card(title, value, unit="", color="#111827"):
    st.markdown(
        f"""
        <div style="
            background-color:white;
            border-radius:18px;
            padding:18px;
            box-shadow:0 4px 12px rgba(0,0,0,.12);
            border-top:6px solid {color};
            min-height:115px;
        ">
            <div style="font-size:14px;color:#6b7280;font-weight:600;">
                {title}
            </div>
            <div style="font-size:27px;font-weight:800;color:#111827;margin-top:8px;">
                {value}
            </div>
            <div style="font-size:13px;color:#6b7280;">
                {unit}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =====================================================
# DATA FROM DATABASE
# =====================================================

@st.cache_data(ttl=300)
def load_dates():
    query = text("""
    SELECT DISTINCT
        load_date
    FROM v_site_simulation_inputs
    ORDER BY load_date DESC
    """)

    df = pd.read_sql(query, engine)

    if df.empty:
        return df

    df["load_date"] = pd.to_datetime(df["load_date"]).dt.date

    return df


@st.cache_data(ttl=300)
def load_sites_by_date(load_date):
    query = text("""
    SELECT
        site_id,
        code_site,
        COALESCE(site_name, '') AS site_name,
        grid_mode,
        grid_status,
        simulation_ready_basic
    FROM v_site_simulation_inputs
    WHERE load_date = :load_date
    ORDER BY code_site
    """)

    return pd.read_sql(
        query,
        engine,
        params={
            "load_date": load_date
        }
    )


def load_site_day_inputs(site_id, load_date):
    query = text("""
    SELECT *
    FROM v_site_simulation_inputs
    WHERE site_id = :site_id
      AND load_date = :load_date
    LIMIT 1
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "site_id": site_id,
            "load_date": load_date
        }
    )

    if df.empty:
        return None

    return df.iloc[0].to_dict()


# =====================================================
# SAVE RESULT OPTIONAL
# =====================================================

def save_result_to_energy_kpi_daily(result):

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


# =====================================================
# SIMULATION
# =====================================================

def run_simulation_from_form(inputs):

    simulation_hours = inputs["simulation_hours"]
    dt = inputs["dt"]

    config = SimulationConfig(
        simulation_hours=simulation_hours,
        dt=dt,
        ems_mode="reliability",
        generator_start_soc=inputs["soc_start_ge_pct"],
        generator_stop_soc=inputs["soc_stop_ge_pct"],
    )

    solar = SolarModel(
        daily_energy_kwh=inputs["daily_solar_kwh"],
        dt=dt
    )

    grid = GridModel(
        availability=inputs["grid_availability_pct"],
        outages=inputs["grid_outages_per_day"],
        dt=dt
    )

    load = Load(
        mode="constant",
        average_power=inputs["avg_power_w"],
        dt=dt
    )

    battery = Battery(
        battery_type=inputs["battery_type"],
        nb_battery=inputs["nb_battery"],
        capacity_ah=inputs["capacity_ah"],
        nominal_voltage=inputs["battery_voltage_v"],
        efficiency=inputs["battery_efficiency_pct"],
        battery_quality=inputs["battery_quality_pct"],
        dod=inputs["dod_pct"],
        soc_initial=inputs["soc_initial_pct"],
        soc_start_charge=inputs["soc_start_charge_pct"],
        soc_stop_charge=inputs["soc_stop_charge_pct"],
        k1=inputs["k1"],
        k2=inputs["k2"],
        dt=dt,
        generator_start_soc=inputs["soc_start_ge_pct"],
        generator_stop_soc=inputs["soc_stop_ge_pct"],
    )

    fuel_curve = {
        25: inputs["fuel_25_lph"],
        50: inputs["fuel_50_lph"],
        75: inputs["fuel_75_lph"],
        100: inputs["fuel_100_lph"],
    }

    generator = Generator(
        rated_power_kw=inputs["generator_power_kw"],
        fuel_curve=fuel_curve,
        dt=dt
    )

    manager = EnergyManager(
        solar=solar,
        grid=grid,
        load=load,
        battery=battery,
        generator=generator,
        config=config
    )

    manager.run()

    summary = manager.summary()

    result = {
        "site_id": inputs["site_id"],
        "kpi_date": inputs["load_date"],

        "load_energy_kwh": f(
            pick(
                summary,
                [
                    "Load Energy (kWh)",
                    "Load Energy kWh",
                    "load_energy_kwh"
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
                    "solar_energy_kwh"
                ],
                0
            )
        ),

        "grid_energy_kwh": f(
            pick(
                summary,
                [
                    "Grid Energy (kWh)",
                    "grid_energy_kwh"
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
                    "battery_discharge_kwh"
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
                    "generator_energy_kwh"
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
                    "fuel_consumption_l"
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
                    "generator_runtime_h"
                ],
                0
            )
        ),

        "generator_starts": i(
            pick(
                summary,
                [
                    "Generator Starts",
                    "generator_starts"
                ],
                0
            )
        ),

        "soc_min_pct": f(
            pick(
                summary,
                [
                    "SOC Min (%)",
                    "soc_min_pct"
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
                    "soc_final_pct"
                ],
                0
            )
        ),

        "unserved_load_kwh": f(
            pick(
                summary,
                [
                    "Unserved Load (kWh)",
                    "unserved_load_kwh"
                ],
                0
            )
        ),

        "load_source": "FORM_ADJUSTED",
        "solar_source": "FORM_ADJUSTED",
        "grid_source": "FORM_ADJUSTED",

        "simulation_hours": simulation_hours,
        "dt_min": dt,
    }

    history = getattr(manager, "history", None)

    if history is None:
        df_history = pd.DataFrame()
    else:
        df_history = pd.DataFrame(history)

    if not df_history.empty:
        if "time_h" not in df_history.columns:
            df_history.insert(
                0,
                "time_h",
                [
                    index * dt / 60
                    for index in range(len(df_history))
                ]
            )

    return result, df_history, summary


# =====================================================
# PAGE
# =====================================================

def show_site_simulation_form():

    st.title("🧪 Simulation énergétique site / jour")

    col_refresh, col_info = st.columns([1, 4])

    with col_refresh:
        if st.button(
            "🔄 Actualiser",
            key="refresh_site_day_simulation"
        ):
            st.cache_data.clear()
            st.rerun()

    with col_info:
        st.caption(
            "Actualise les inputs depuis v_site_simulation_inputs."
        )

        st.caption(
            "Cette page permet de charger les données journalières d’un site, "
            "ajuster les inputs, puis lancer une simulation énergétique."
        )

        df_dates = load_dates()

        if df_dates.empty:
            st.warning("Aucune date trouvée dans v_site_simulation_inputs.")
            return

    selected_date = st.sidebar.selectbox(
        "Date de simulation",
        df_dates["load_date"].tolist(),
        index=0,
        key="form_sim_date"
    )

    df_sites = load_sites_by_date(selected_date)

    if df_sites.empty:
        st.warning("Aucun site trouvé pour cette date.")
        return

    show_only_ready = st.sidebar.checkbox(
        "Afficher uniquement les sites prêts",
        value=False,
        key="form_show_ready"
    )

    if show_only_ready:
        df_sites = df_sites[
            df_sites["simulation_ready_basic"] == True
        ].copy()

    if df_sites.empty:
        st.warning("Aucun site prêt pour cette date.")
        return

    df_sites["label"] = (
        df_sites["code_site"].astype(str)
        + " - "
        + df_sites["site_name"].astype(str)
        + " | "
        + df_sites["grid_mode"].fillna("NO_GRID").astype(str)
    )

    selected_site_label = st.sidebar.selectbox(
        "Site",
        df_sites["label"].tolist(),
        key="form_sim_site"
    )

    site_id = int(
        df_sites.loc[
            df_sites["label"] == selected_site_label,
            "site_id"
        ].iloc[0]
    )

    row = load_site_day_inputs(
        site_id=site_id,
        load_date=selected_date
    )

    if row is None:
        st.warning("Impossible de charger les inputs du site.")
        return

    st.info(
        f"Site sélectionné : {row.get('code_site')} | "
        f"Date : {selected_date} | "
        f"Grid : {row.get('grid_mode')} | "
        f"Simulation ready : {row.get('simulation_ready_basic')}"
    )

    # =====================================================
    # FORMULAIRE
    # =====================================================

    with st.form(
        key="energy_site_day_form"
    ):

        st.subheader("1️⃣ Paramètres généraux")

        c1, c2, c3 = st.columns(3)

        with c1:
            simulation_hours = st.number_input(
                "Durée simulation (h)",
                min_value=1,
                max_value=168,
                value=24,
                step=1
            )

        with c2:
            dt = st.selectbox(
                "Pas simulation (min)",
                [5, 10, 15, 30],
                index=0
            )

        with c3:
            save_to_db = st.checkbox(
                "Enregistrer dans energy_kpi_daily",
                value=False
            )

        st.divider()

        st.subheader("2️⃣ Load journalier")

        avg_power_w = st.number_input(
            "Load moyen DC / AC équivalent (W)",
            min_value=0.0,
            value=f(row.get("avg_power_w"), 0),
            step=100.0
        )

        st.caption(
            f"Source load actuelle : {row.get('load_source')}"
        )

        st.divider()

        st.subheader("3️⃣ Solaire")

        c1, c2, c3 = st.columns(3)

        with c1:
            daily_solar_kwh = st.number_input(
                "Production solaire journalière (kWh/j)",
                min_value=0.0,
                value=f(row.get("daily_solar_kwh"), 0),
                step=1.0
            )

        with c2:
            panel_quantity = st.number_input(
                "Nombre panneaux",
                min_value=0,
                value=i(row.get("panel_quantity"), 0),
                step=1
            )

        with c3:
            panel_power_wc = st.number_input(
                "Puissance panneau (Wc)",
                min_value=0.0,
                value=f(row.get("panel_power_wc"), 0),
                step=10.0
            )

        st.caption(
            f"Source solaire actuelle : {row.get('solar_source')}"
        )

        st.divider()

        st.subheader("4️⃣ Grid")

        grid_mode_options = [
            "ON_GRID",
            "OFF_GRID",
            "LOSTCOM"
        ]

        current_grid_mode = str(
            row.get("grid_mode") or "ON_GRID"
        ).upper().strip()

        if current_grid_mode not in grid_mode_options:
            current_grid_mode = "ON_GRID"

        c1, c2, c3 = st.columns(3)

        with c1:
            grid_mode = st.selectbox(
                "Mode Grid",
                grid_mode_options,
                index=grid_mode_options.index(current_grid_mode)
            )

        with c2:
            grid_availability_pct = st.number_input(
                "Disponibilité Grid (%)",
                min_value=0.0,
                max_value=100.0,
                value=f(row.get("grid_availability_pct"), 0),
                step=1.0
            )

        with c3:
            grid_outages_per_day = st.number_input(
                "Nombre coupures / jour",
                min_value=0,
                value=i(row.get("grid_outages_per_day"), 0),
                step=1
            )

        if grid_mode == "OFF_GRID":
            grid_availability_pct = 0.0
            grid_outages_per_day = 0

            st.warning(
                "Mode OFF_GRID sélectionné : disponibilité forcée à 0 %, coupures à 0."
            )

        st.caption(
            f"Source grid actuelle : {row.get('grid_source')} | "
            f"Status : {row.get('grid_status')}"
        )

        st.divider()

        st.subheader("5️⃣ Groupe électrogène")

        c1, c2, c3 = st.columns(3)

        with c1:
            generator_power_kva = st.number_input(
                "Puissance GE (kVA)",
                min_value=0.0,
                value=f(row.get("generator_power_kva"), 0),
                step=5.0
            )

        with c2:
            generator_power_kw = st.number_input(
                "Puissance GE (kW)",
                min_value=0.0,
                value=f(row.get("generator_power_kw"), 0),
                step=5.0
            )

        with c3:
            st.caption("Courbe carburant GE")

        c4, c5, c6, c7 = st.columns(4)

        with c4:
            fuel_25_lph = st.number_input(
                "Fuel 25 % (L/h)",
                min_value=0.0,
                value=f(row.get("fuel_25_lph"), 1.5),
                step=0.1
            )

        with c5:
            fuel_50_lph = st.number_input(
                "Fuel 50 % (L/h)",
                min_value=0.0,
                value=f(row.get("fuel_50_lph"), 3.0),
                step=0.1
            )

        with c6:
            fuel_75_lph = st.number_input(
                "Fuel 75 % (L/h)",
                min_value=0.0,
                value=f(row.get("fuel_75_lph"), 4.5),
                step=0.1
            )

        with c7:
            fuel_100_lph = st.number_input(
                "Fuel 100 % (L/h)",
                min_value=0.0,
                value=f(row.get("fuel_100_lph"), 6.0),
                step=0.1
            )

        st.divider()

        st.subheader("6️⃣ Batteries")

        battery_type_options = [
            "ACID",
            "Lithium"
        ]

        current_battery_type = str(
            row.get("battery_type") or "ACID"
        ).strip()

        if current_battery_type.upper() == "LITHIUM":
            current_battery_type = "Lithium"
        else:
            current_battery_type = "ACID"

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            battery_type = st.selectbox(
                "Type batterie",
                battery_type_options,
                index=battery_type_options.index(current_battery_type)
            )

        with c2:
            nb_battery = st.number_input(
                "Nombre batteries",
                min_value=1,
                value=max(i(row.get("nb_battery"), 1), 1),
                step=1
            )

        with c3:
            capacity_ah = st.number_input(
                "Capacité batterie (Ah)",
                min_value=1.0,
                value=max(f(row.get("capacity_ah"), 100), 1.0),
                step=50.0
            )

        with c4:
            battery_voltage_v = st.number_input(
                "Tension nominale (V)",
                min_value=12.0,
                value=f(row.get("battery_voltage_v"), 48),
                step=12.0
            )

        c5, c6, c7, c8 = st.columns(4)

        with c5:
            battery_efficiency_pct = st.number_input(
                "Rendement batterie (%)",
                min_value=1.0,
                max_value=100.0,
                value=f(row.get("battery_efficiency_pct"), 95),
                step=1.0
            )

        with c6:
            battery_quality_pct = st.number_input(
                "Qualité batterie (%)",
                min_value=1.0,
                max_value=100.0,
                value=f(row.get("battery_quality_pct"), 100),
                step=1.0
            )

        with c7:
            dod_pct = st.number_input(
                "DoD (%)",
                min_value=1.0,
                max_value=100.0,
                value=f(row.get("dod_pct"), 80),
                step=1.0
            )

        with c8:
            soc_initial_pct = st.number_input(
                "SOC initial (%)",
                min_value=0.0,
                max_value=100.0,
                value=f(row.get("soc_initial_pct"), 80),
                step=1.0
            )

        c9, c10, c11, c12 = st.columns(4)

        with c9:
            soc_start_ge_pct = st.number_input(
                "SOC démarrage GE (%)",
                min_value=0.0,
                max_value=100.0,
                value=f(row.get("soc_start_ge_pct"), 50),
                step=1.0
            )

        with c10:
            soc_stop_ge_pct = st.number_input(
                "SOC arrêt GE (%)",
                min_value=0.0,
                max_value=100.0,
                value=f(row.get("soc_stop_ge_pct"), 95),
                step=1.0
            )

        with c11:
            soc_start_charge_pct = st.number_input(
                "SOC début charge (%)",
                min_value=0.0,
                max_value=100.0,
                value=f(row.get("soc_start_charge_pct"), 50),
                step=1.0
            )

        with c12:
            soc_stop_charge_pct = st.number_input(
                "SOC fin charge (%)",
                min_value=0.0,
                max_value=100.0,
                value=f(row.get("soc_stop_charge_pct"), 95),
                step=1.0
            )

        c13, c14 = st.columns(2)

        with c13:
            k1 = st.number_input(
                "K1 charge",
                min_value=0.0,
                max_value=2.0,
                value=f(row.get("k1"), 0.20),
                step=0.01
            )

        with c14:
            k2 = st.number_input(
                "K2 charge ACID",
                min_value=0.0,
                max_value=2.0,
                value=f(row.get("k2"), 0.05),
                step=0.01
            )

        submitted = st.form_submit_button(
            "▶ Lancer la simulation"
        )

    # =====================================================
    # RUN
    # =====================================================

    if submitted:

        inputs = {
            "site_id": site_id,
            "code_site": row.get("code_site"),
            "load_date": selected_date,

            "simulation_hours": int(simulation_hours),
            "dt": int(dt),

            "avg_power_w": float(avg_power_w),

            "daily_solar_kwh": float(daily_solar_kwh),
            "panel_quantity": int(panel_quantity),
            "panel_power_wc": float(panel_power_wc),

            "grid_mode": grid_mode,
            "grid_availability_pct": float(grid_availability_pct),
            "grid_outages_per_day": int(grid_outages_per_day),

            "generator_power_kva": float(generator_power_kva),
            "generator_power_kw": float(generator_power_kw),
            "fuel_25_lph": float(fuel_25_lph),
            "fuel_50_lph": float(fuel_50_lph),
            "fuel_75_lph": float(fuel_75_lph),
            "fuel_100_lph": float(fuel_100_lph),

            "battery_type": battery_type,
            "nb_battery": int(nb_battery),
            "capacity_ah": float(capacity_ah),
            "battery_voltage_v": float(battery_voltage_v),
            "battery_efficiency_pct": float(battery_efficiency_pct),
            "battery_quality_pct": float(battery_quality_pct),
            "dod_pct": float(dod_pct),
            "soc_initial_pct": float(soc_initial_pct),
            "soc_start_ge_pct": float(soc_start_ge_pct),
            "soc_stop_ge_pct": float(soc_stop_ge_pct),
            "soc_start_charge_pct": float(soc_start_charge_pct),
            "soc_stop_charge_pct": float(soc_stop_charge_pct),
            "k1": float(k1),
            "k2": float(k2),
        }

        result, df_history, summary = run_simulation_from_form(
            inputs
        )

        st.session_state["last_energy_form_result"] = result
        st.session_state["last_energy_form_history"] = df_history
        st.session_state["last_energy_form_inputs"] = inputs

        if save_to_db:

            save_result_to_energy_kpi_daily(result)

            st.success(
                "Résultat enregistré dans energy_kpi_daily avec source FORM_ADJUSTED."
            )

        else:

            st.success(
                "Simulation terminée. Résultat affiché sans écraser energy_kpi_daily."
            )

    # =====================================================
    # DISPLAY RESULT
    # =====================================================

    if "last_energy_form_result" not in st.session_state:
        return

    result = st.session_state["last_energy_form_result"]
    df_history = st.session_state.get(
        "last_energy_form_history",
        pd.DataFrame()
    )

    st.divider()

    st.subheader("✅ Résultats de simulation")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        kpi_card(
            "Load",
            f"{result['load_energy_kwh']:,.2f}",
            "kWh",
            "#2563eb"
        )

    with c2:
        kpi_card(
            "Solaire",
            f"{result['solar_energy_kwh']:,.2f}",
            "kWh",
            "#f59e0b"
        )

    with c3:
        kpi_card(
            "Grid",
            f"{result['grid_energy_kwh']:,.2f}",
            "kWh",
            "#16a34a"
        )

    with c4:
        kpi_card(
            "GE",
            f"{result['generator_energy_kwh']:,.2f}",
            "kWh",
            "#111827"
        )

    st.write("")

    c5, c6, c7, c8 = st.columns(4)

    with c5:
        kpi_card(
            "Heures GE",
            f"{result['generator_runtime_h']:,.2f}",
            "h",
            "#f97316"
        )

    with c6:
        kpi_card(
            "Fuel GE",
            f"{result['fuel_consumption_l']:,.2f}",
            "L",
            "#dc2626"
        )

    with c7:
        kpi_card(
            "SOC final",
            f"{result['soc_final_pct']:,.1f}",
            "%",
            "#7c3aed"
        )

    with c8:
        kpi_card(
            "Load non servi",
            f"{result['unserved_load_kwh']:,.3f}",
            "kWh",
            "#b91c1c"
        )

    st.divider()

    st.subheader("⚡ Répartition énergie")

    df_energy = pd.DataFrame(
        [
            {
                "Source": "Load",
                "kWh": result["load_energy_kwh"]
            },
            {
                "Source": "Solaire",
                "kWh": result["solar_energy_kwh"]
            },
            {
                "Source": "Grid",
                "kWh": result["grid_energy_kwh"]
            },
            {
                "Source": "GE",
                "kWh": result["generator_energy_kwh"]
            },
            {
                "Source": "Batterie",
                "kWh": result["battery_discharge_kwh"]
            },
        ]
    )

    fig_energy = go.Figure()

    fig_energy.add_trace(
        go.Bar(
            x=df_energy["Source"],
            y=df_energy["kWh"],
            text=df_energy["kWh"].round(2),
            textposition="outside"
        )
    )

    fig_energy.update_layout(
        height=450,
        title="Énergie par source",
        xaxis_title="Source",
        yaxis_title="kWh"
    )

    st.plotly_chart(
        fig_energy,
        use_container_width=True,
        key="form_chart_energy_sources"
    )

    if not df_history.empty:

        st.divider()

        st.subheader("📈 Historique simulation")

        st.dataframe(
            df_history.tail(50),
            use_container_width=True,
            height=350
        )

    st.divider()

    st.subheader("📋 Résultat brut")

    st.dataframe(
        pd.DataFrame([result]),
        use_container_width=True
    )