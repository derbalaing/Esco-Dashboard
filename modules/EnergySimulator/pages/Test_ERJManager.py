import streamlit as st
import plotly.express as px

from models.simulation_config import SimulationConfig
from models.solar import SolarModel
from models.grid import GridModel
from models.load import Load
from models.battery import Battery
from models.generator import Generator
from models.energy_manager import EnergyManager


st.set_page_config(
    page_title="Test EnergyManager",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Test EnergyManager")

with st.sidebar:

    st.header("Simulation")

    simulation_hours = st.number_input(
        "Durée simulation (h)",
        min_value=1,
        max_value=168,
        value=24,
    )

    dt = st.selectbox(
        "Pas de temps (min)",
        [5, 10, 15],
        index=0,
    )

    st.header("Solaire")

    daily_solar = st.number_input(
        "Production solaire (kWh/jour)",
        min_value=0.0,
        max_value=200.0,
        value=30.0,
        step=1.0,
    )

    st.header("Grid")
    grid_mode = st.selectbox(
        "Mode Grid",
        ["On-grid", "Off-grid"],
    )
    if grid_mode == "Off-grid":

        grid_availability = 0
        outages = 0

        st.info("Mode off-grid : le Grid est toujours indisponible.")

    else:

        grid_availability = st.slider(
            "Disponibilité Grid (%)",
            0,
            100,
            100,
        )

        if grid_availability == 100:

            outages = 0

            st.number_input(
                "Nombre de coupures Grid",
                min_value=0,
                max_value=0,
                value=0,
                disabled=True,
            )

        elif grid_availability == 0:

            outages = 0

            st.number_input(
                "Nombre de coupures Grid",
                min_value=0,
                max_value=0,
                value=0,
                disabled=True,
            )

            st.info("Grid indisponible 0 % : comportement équivalent à un site off-grid.")

        else:

            outages = st.number_input(
                "Nombre de coupures Grid",
                min_value=1,
                max_value=50,
                value=4,
            )

    st.header("Load")

    load_power = st.number_input(
        "Load moyen (W)",
        min_value=100.0,
        max_value=50000.0,
        value=2500.0,
        step=100.0,
    )

    st.header("Batteries")

    battery_type = st.selectbox(
        "Type batterie",
        ["Lithium", "ACID"],
    )

    nb_battery = st.number_input(
        "Nombre batteries 48V",
        min_value=1,
        max_value=100,
        value=4,
    )

    capacity_ah = st.number_input(
        "Capacité batterie (Ah)",
        min_value=10.0,
        max_value=5000.0,
        value=100.0,
        step=10.0,
    )

    soc_initial = st.slider(
        "SOC initial (%)",
        0,
        100,
        80,
    )

    battery_quality = st.slider(
        "Qualité batteries (%)",
        min_value=10,
        max_value=100,
        value=100,
        step=5,
    )

    dod = st.slider(
        "DoD (%)",
        10,
        100,
        80,
    )

    k1 = st.number_input(
        "K1",
        min_value=0.01,
        max_value=1.0,
        value=0.20,
        step=0.01,
    )

    k2 = st.number_input(
        "K2",
        min_value=0.01,
        max_value=1.0,
        value=0.05,
        step=0.01,
    )

    st.header("GE")

    ge_power = st.number_input(
        "Puissance GE (kW)",
        min_value=1.0,
        max_value=500.0,
        value=15.0,
        step=1.0,
    )

    start_soc = st.slider(
        "SOC démarrage GE (%)",
        0,
        100,
        50,
    )

    stop_soc = st.slider(
        "SOC arrêt GE (%)",
        0,
        100,
        95,
    )

    run = st.button(
        "▶ Lancer simulation",
        use_container_width=True,
    )


if run:

    config = SimulationConfig(
        simulation_hours=simulation_hours,
        dt=dt,
        ems_mode="Reliability",
        generator_start_soc=start_soc,
        generator_stop_soc=stop_soc,
    )

    solar = SolarModel(
        daily_energy_kwh=daily_solar,
        dt=dt,
    )

    grid = GridModel(
        availability=grid_availability,
        outages=outages,
        dt=dt,
        seed=42,
    )

    load = Load(
        mode="constant",
        average_power=load_power,
        dt=dt,
    )

    battery = Battery(
        battery_type=battery_type,
        nb_battery=nb_battery,
        capacity_ah=capacity_ah,
        battery_quality=battery_quality,
        soc_initial=soc_initial,
        dod=dod,
        k1=k1,
        k2=k2,
        dt=dt,
        generator_start_soc=start_soc,
        generator_stop_soc=stop_soc,
    )

    generator = Generator(
        rated_power_kw=ge_power,
        dt=dt,
    )

    manager = EnergyManager(
        solar=solar,
        battery=battery,
        grid=grid,
        generator=generator,
        load=load,
        config=config
    )
    df = manager.run()


    st.write("Grid availability réelle (%) :", df["Grid Available"].mean() * 100)

    st.dataframe(
        df[
            [
                "Hour",
                "Grid Available",
                "Solar Power (W)",
                "Load Power (W)",
                "grid_to_load",
                "battery_to_load",
                "generator_to_load",
                "generator_to_battery",
                "unserved_load",
                "Battery SOC (%)",
                "Generator Running",
            ]
        ].head(50)
    )



    summary = manager.summary()
    battery_summary = battery.summary()

    st.subheader("KPI")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Production solaire",
        f"{summary['Solar Production (kWh)']:.2f} kWh",
    )

    c2.metric(
        "Énergie Grid",
        f"{summary['Grid Energy (kWh)']:.2f} kWh",
    )

    c3.metric(
        "Fuel GE",
        f"{summary['Fuel Consumption (L)']:.2f} L",
    )

    c4.metric(
        "Heures GE",
        f"{summary['Generator Running Hours']:.2f} h",
    )

    c5, c6, c7, c8 = st.columns(4)

    c5.metric(
        "SOC min",
        f"{summary['SOC Min (%)']:.1f} %",
    )

    c6.metric(
        "SOC final",
        f"{summary['SOC Final (%)']:.1f} %",
    )

    c7.metric(
        "PV perdu",
        f"{summary['Solar Lost (kWh)']:.2f} kWh",
    )

    c8.metric(
        "Load non servi",
        f"{summary['Unserved Load (kWh)']:.2f} kWh",
    )

    st.subheader("Courbes")

   
    fig = px.line(
        df,
        x="Hour",
        y="Battery SOC (%)",
        title="SOC Batteries",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="chart_soc_battery",
    )


    fig = px.line(
        df,
        x="Hour",
        y=[
            "Solar Power (W)",
            "Load Power (W)",
            "Generator Power (W)",
        ],
        title="Puissances principales",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="chart_main_power",
    )


    fig = px.line(
        df,
        x="Hour",
        y="Battery Current (A)",
        title="Courant batterie",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="chart_battery_current",
    )


    fig = px.line(
        df,
        x="Hour",
        y="Battery Power (W)",
        title="Puissance batterie",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="chart_battery_power",
    )


    fig = px.line(
        df,
        x="Hour",
        y="Grid Available",
        title="Disponibilité Grid",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="chart_grid_available",
    )


    fig = px.line(
        df,
        x="Hour",
        y="Generator Fuel Total (L)",
        title="Fuel GE cumulé",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="chart_generator_fuel",
    )

else:

    st.info(
        "Configurez les paramètres à gauche puis cliquez sur Lancer simulation."
    )


