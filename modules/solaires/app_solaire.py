from streamlit_option_menu import option_menu

import streamlit as st

from modules.solaires.dashboard_solar import show_dashboard
from modules.solaires.dashboard_par_site import show
from modules.solaires.alerte_solaire import show as show_alertes
from modules.solaires.gestion_alertes import show as show_gestion
from modules.solaires.dashboard_solar_sites_summary import show_solar_sites_summary

if st.button("🏠 Retour à l'accueil"):
    st.session_state.module = None
    st.rerun()
    
def show_solaire():

    st.button(
        "⬅ Retour à l'accueil",
        on_click=lambda: st.session_state.pop("module")
    )

    selected = option_menu(
        menu_title=None,
        options=[
            "Dashboard",
            "Analyse Site",
            "Alertes",
            "Gestion Alertes",
            "Taleau des sites solaires"
        ],
        icons=[
            "bar-chart",
            "geo-alt",
            "bell",
            "tools",
            "tools"
        ],
        orientation="horizontal"
    )

    if selected == "Dashboard":
        show_dashboard()

    elif selected == "Analyse Site":
        show()

    elif selected == "Alertes":
        show_alertes()

    elif selected == "Gestion Alertes":
        show_gestion()

    elif selected == "Taleau des sites solaires":
        show_solar_sites_summary()