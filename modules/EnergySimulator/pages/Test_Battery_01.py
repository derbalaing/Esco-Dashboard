import streamlit as st
import plotly.express as px
from models.battery import Battery

st.set_page_config(
    page_title="Battery Simulator",
    page_icon="🔋",
    layout="wide"
)

st.title("🔋 Battery Simulator")

# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.header("Configuration")

battery_type = st.sidebar.selectbox(
    "Battery Type",
    ["Lithium", "ACID"]
)

nb_battery = st.sidebar.number_input(
    "Number of Batteries",
    1,
    20,
    4
)

capacity = st.sidebar.number_input(
    "Capacity (Ah)",
    50,
    1500,
    100
)

soc = st.sidebar.slider(
    "Initial SOC (%)",
    20,
    100,
    80
)

efficiency = st.sidebar.slider(
    "Efficiency (%)",
    70,
    100,
    95
)

dod = st.sidebar.slider(
    "DoD (%)",
    50,
    100,
    80
)

mode = st.sidebar.radio(
    "Simulation Mode",
    ["charge", "discharge"]
)

duration = st.sidebar.slider(
    "Duration (hours)",
    1,
    24,
    8
)

load = st.sidebar.number_input(
    "Load (W)",
    100,
    10000,
    2500
)


k1 = st.sidebar.slider(
    "K1",
    0.05,
    0.50,
    0.20
)

k2 = st.sidebar.slider(
    "K2",
    0.01,
    0.20,
    0.05
)

run = st.sidebar.button("▶ Run Simulation")

# =====================================================

if run:

    battery = Battery(

        battery_type=battery_type,

        nb_battery=nb_battery,

        capacity_ah=capacity,

        efficiency=efficiency,

        dod=dod,

        soc_initial=soc,

        k1=k1,

        k2=k2

    )

    df = battery.simulate(

        mode=mode,

        duration_hours=duration,

        load_power=load

    )

    summary = battery.summary()

    st.success("Simulation Finished")

    # ================================================
    # KPI
    # ================================================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "SOC Final",
        f"{summary['SOC Final']:.1f} %"
    )

    c2.metric(
        "Voltage",
        f"{summary['Voltage Final']:.2f} V"
    )

    c3.metric(
        "Current",
        f"{summary['Current Final']:.2f} A"
    )

    c4.metric(
        "Energy",
        f"{summary['Energy Final']/1000:.2f} kWh"
    )

    # ================================================
    # SOC
    # ================================================

    fig = px.line(
        df,
        x="time",
        y="soc",
        title="SOC Evolution"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ================================================
    # Voltage
    # ================================================

    fig = px.line(
        df,
        x="time",
        y="voltage",
        title="Battery Voltage"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ================================================
    # Current
    # ================================================

    fig = px.line(
        df,
        x="time",
        y="current",
        title="Battery Current"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ================================================
    # Energy
    # ================================================

    fig = px.line(
        df,
        x="time",
        y="energy",
        title="Battery Energy"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ================================================
    # Table
    # ================================================

    st.subheader("Simulation Results")

    st.dataframe(
        df,
        use_container_width=True
    )

    csv = df.to_csv(index=False).encode()

    st.download_button(

        "📥 Download CSV",

        csv,

        "battery_simulation.csv",

        "text/csv"

    )