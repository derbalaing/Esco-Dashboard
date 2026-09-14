import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Nettoyage si Python a déjà chargé un mauvais module "config"
if "config" in sys.modules:
    config_module = sys.modules["config"]

    if not hasattr(config_module, "__path__"):
        del sys.modules["config"]


import streamlit as st

from modules.accueil import accueil
from modules.solaires.app_solaire import show_solaire
from modules.genset.app_ge import show_ge
from modules.batteries.app_batterie import show_batterie
from modules.sites.app_site import show_site
from modules.powercore.app_powercore import show_powercore
from modules.grid.app_grid import show_grid

st.set_page_config(
    page_title="ESCO Monitoring",
    page_icon="⚡",
    layout="wide"
)


st.markdown("""
        <style>

        .stApp{
            background-color:#f5f7fb;
        }

        /* Carte */
        .card{
            background:white;
            border-radius:18px;
            padding:20px;
            margin-bottom:20px;

            box-shadow:
                0 4px 12px rgba(0,0,0,0.08);

            border:1px solid #ececec;
        }

        /* Titre */
        .card-title{
            font-size:22px;
            font-weight:700;
            color:#1f2937;
            margin-bottom:15px;
        }

        /* Sous titre */
        .card-subtitle{
            color:#777;
            font-size:14px;
            margin-bottom:10px;
        }

                    
        .chart-title{

            background:white;

            padding:18px;

            border-radius:15px;

            box-shadow:0 3px 10px rgba(0,0,0,.08);

            border-left:6px solid #ff9800;

            margin-bottom:10px;
        }

        .chart-title h3{

            margin:0;

            color:#1f2937;

            font-weight:700;
        }

        .chart-title p{

            margin:5px 0 0 0;

            color:#777;

            font-size:14px;
        }

        .kpi-card{
            background:#ffffff;
            padding:20px;
            border-radius:18px;
            box-shadow:0px 3px 12px rgba(0,0,0,0.08);
            border-left:6px solid #f39c12;
        }
                
        .production-card{
            background:#ffffff;
            padding:20px;
            border-radius:18px;
            box-shadow:0px 3px 12px rgba(0,0,0,0.08);
            border-left:6px solid #2ecc71;;
        }   
        .blue-card{
            background:#ffffff;
            padding:20px;
            border-radius:18px;
            box-shadow:0px 3px 12px rgba(0,0,0,0.08);
            border-left:6px solid #3498db;;
        } 
        .black-card{
            background:#ffffff;
            padding:20px;
            border-radius:18px;
            box-shadow:0px 3px 12px rgba(0,0,0,0.08);
            border-left:6px solid #000000;;
        }           

        .kpi-title{
            color:#777;
            font-size:15px;
        }

        .kpi-value{
            font-size:34px;
            font-weight:bold;
            color:#1b263b;
        }

            

            /* Carte graphique */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#gap_cards){

        background:white;

        border-radius:18px;

        padding:20px;

        box-shadow:0 4px 12px rgba(0,0,0,.10);

        border-top:6px solid #ff9800;

        }
            
</style>
""", unsafe_allow_html=True)


# Initialisation
if "module" not in st.session_state:
    st.session_state.module = None

# Affichage
if st.session_state.module is None:
    accueil()

elif st.session_state.module == "SOLAIRE":
    show_solaire()

elif st.session_state.module == "GE":
    show_ge()

elif st.session_state.module == "BATTERY":
    show_batterie()

elif st.session_state.module == "SITE":
    show_site()

elif st.session_state.module == "POWERCORE":
    show_powercore()

elif st.session_state.module == "GRID":
    show_grid()