from streamlit_option_menu import option_menu

import streamlit as st

from modules.powercore.dashboard_powercore import show_dashboard_powercore


def show_powercore():

    st.button(
        "⬅ Retour à l'accueil",
        on_click=lambda: st.session_state.pop("module")
    )

    selected = option_menu(
        menu_title=None,
        options=[
            "Dashboard powercore",
            "Analyse powercore",
            "Alarmes powercore"
        ],
        icons=[
            "speedometer",
            "graph-up",
            "bell"
        ],
        orientation="horizontal"
    )

    if selected == "Dashboard Powercore":
        show_dashboard_powercore()