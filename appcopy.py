import streamlit as st
from streamlit_option_menu import option_menu


import modules.dashboard_solar as dashboard_solar
import modules.dashboard_par_site as dashboard_par_site
import modules.alerte_solaire as alertes_solaires
import modules.gestion_alertes as gestion_alertes

st.set_page_config(
    page_title="Solar Monitoring",
    page_icon="☀️",
    layout="wide"
)

selected = option_menu(
    menu_title=None,

    options=[
        "Dashboard",
        "Analyse Site",
        "Alertes",
        "Gestion Alertes"
    ],

    icons=[
        "bar-chart",
        "geo-alt",
        "exclamation-triangle",
        "tools"
    ],

    orientation="horizontal"
)

if selected  == "Dashboard":
    dashboard_solar.show_dashboard()

elif selected  == "Analyse Site":
    dashboard_par_site.show()

elif selected  == "Alertes":
    alertes_solaires.show()

elif selected  == "Gestion Alertes":
    gestion_alertes.show()
   