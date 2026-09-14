from streamlit_option_menu import option_menu

import streamlit as st

from modules.sites.dashboard_site import show_dashboard_site


def show_site():

    st.button(
        "⬅ Retour à l'accueil",
        on_click=lambda: st.session_state.pop("module")
    )

    selected = option_menu(
        menu_title=None,
        options=[
            "Dashboard Site",
            "Analyse Site",
            "Alarmes Site"
        ],
        icons=[
            "speedometer",
            "graph-up",
            "bell"
        ],
        orientation="horizontal"
    )

    if selected == "Dashboard Site":
        show_dashboard_site()