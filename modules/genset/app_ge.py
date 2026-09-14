from streamlit_option_menu import option_menu

import streamlit as st

from modules.genset.dashboard_ge import show_dashboard_ge
from modules.genset.dashboard_ge_par_site import show_ge_site_analysis
from modules.genset.simulation_site_form import show_site_simulation_form
from modules.genset.simulation_fuel import show_simulation_fuel

def show_ge():

    st.button(
        "⬅ Retour à l'accueil",
        on_click=lambda: st.session_state.pop("module")
    )

    selected = option_menu(
        menu_title=None,
        options=[
            "Dashboard GE",
            "Analyse GE par site",
            
            "Simulation site / jour",
            "Simulation fuel /site /jour"
            "Alarmes GE"
        ],
        icons=[
            "speedometer",
            "graph-up",
            "graph-up",
            "graph-up",
            "bell"
        ],
        orientation="horizontal"
    )

    if selected == "Dashboard GE":
        show_dashboard_ge()

    elif selected == "Analyse GE par site":
        show_ge_site_analysis()

    elif selected == "Simulation site / jour":
        show_site_simulation_form()

        
    elif selected == "Simulation fuel /site /jour":
        show_simulation_fuel()