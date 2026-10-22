
import streamlit as st

from modules.project.dashboard_interventions import show_interventions_dashboard

# Configuration de la page
st.set_page_config(
    page_title="Suivi des interventions terrain",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Ouvrir directement le module Interventions
show_interventions_dashboard()
