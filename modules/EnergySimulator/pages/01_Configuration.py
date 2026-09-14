import streamlit as st
from config import DEFAULT_CONFIG


st.title("⚙ Configuration du système")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Load",
        "PV",
        "Grid",
        "Batteries",
        "GE"
    ]
)

####################################################
# LOAD
####################################################

with tab1:

    st.subheader("Charge Télécom")

    load = st.number_input(
        "Puissance de la charge (W)",
        value=DEFAULT_CONFIG["load"],
        step=100
    )

####################################################
# SOLAR
####################################################

with tab2:

    st.subheader("Installation Solaire")

    pv = st.number_input(
        "Puissance installée (kWc)",
        value=DEFAULT_CONFIG["pv_kwc"],
        step=1.0
    )

####################################################
# GRID
####################################################

with tab3:

    st.subheader("Grid")

    availability = st.slider(
        "Disponibilité (%)",
        0,
        100,
        DEFAULT_CONFIG["grid_availability"]
    )

    outages = st.number_input(
        "Nombre de coupures/jour",
        value=DEFAULT_CONFIG["grid_outages"]
    )

####################################################
# BATTERY
####################################################

with tab4:

    st.subheader("Batteries")

    battery_type = st.selectbox(
        "Type",
        [
            "Lithium",
            "ACID"
        ]
    )

    nb = st.number_input(
        "Nombre de batteries",
        value=DEFAULT_CONFIG["battery_number"]
    )

    capacity = st.number_input(
        "Capacité (Ah)",
        value=DEFAULT_CONFIG["battery_capacity"]
    )

    efficiency = st.slider(
        "Rendement (%)",
        70,
        100,
        DEFAULT_CONFIG["battery_efficiency"]
    )

    dod = st.slider(
        "DoD (%)",
        50,
        100,
        DEFAULT_CONFIG["battery_dod"]
    )

    soc0 = st.slider(
        "SOC initial (%)",
        0,
        100,
        DEFAULT_CONFIG["soc_initial"]
    )

    st.divider()

    if battery_type=="Lithium":

        current = st.number_input(
            "Courant de charge (A)",
            value=DEFAULT_CONFIG["charge_current"]
        )

    else:

        k1 = st.number_input(
            "K1 (20%C)",
            value=DEFAULT_CONFIG["k1"]
        )

        k2 = st.number_input(
            "K2 (5%C)",
            value=DEFAULT_CONFIG["k2"]
        )

####################################################
# GE
####################################################

with tab5:

    st.subheader("Groupe Electrogène")

    cph = st.number_input(
        "Consommation (L/h)",
        value=DEFAULT_CONFIG["genset_cph"]
    )

    soc_start = st.slider(
        "SOC démarrage GE (%)",
        0,
        100,
        DEFAULT_CONFIG["soc_start_ge"]
    )

    soc_stop = st.slider(
        "SOC arrêt GE (%)",
        0,
        100,
        DEFAULT_CONFIG["soc_stop_ge"]
    )

####################################################
# SAVE
####################################################

st.divider()

if st.button("💾 Enregistrer la configuration", use_container_width=True):

    st.session_state["config"] = {

        "load":load,

        "pv_kwc":pv,

        "grid_availability":availability,

        "grid_outages":outages,

        "battery_type":battery_type,

        "battery_number":nb,

        "battery_capacity":capacity,

        "battery_efficiency":efficiency,

        "battery_dod":dod,

        "soc_initial":soc0,

        "genset_cph":cph,

        "soc_start_ge":soc_start,

        "soc_stop_ge":soc_stop,

    }

    if battery_type=="Lithium":

        st.session_state["config"]["charge_current"]=current

    else:

        st.session_state["config"]["k1"]=k1
        st.session_state["config"]["k2"]=k2

    st.success("Configuration enregistrée.")