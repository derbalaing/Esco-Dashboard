import streamlit as st

from modules.solaires.app_solaire import show_solaire
from modules.genset.app_ge import show_ge
from modules.sites.app_site import show_site
from modules.batteries.app_batterie import show_batterie
from modules.powercore.app_powercore import show_powercore
from modules.grid.app_grid import show_grid

def accueil():

    st.title("⚡ ESCO Monitoring Platform")

    st.markdown("## Choisissez le système à superviser")

    col1, col2, col3, col4, col5, col6  = st.columns(6)

    with col1:

        st.image(
            "assets/solar.png",
            use_container_width=True,
            width=300
        )

        st.subheader("☀️ Solaire")

        if st.button(
            "Ouvrir Dashboard Solaire",
            use_container_width=True
        ):
            st.session_state["module"] = "SOLAIRE"
            st.rerun()

    with col2:

        st.image(
            "assets/GE.png",
            use_container_width=True,
            width=300
        )

        st.subheader("⚙️ Genset")

        if st.button(
            "Ouvrir Dashboard GE",
            use_container_width=True
        ):
            st.session_state["module"] = "GE"
            st.rerun()


        
    with col3:

        st.image(
            "assets/site.png",
            use_container_width=True
        )

        st.subheader("☀️ Site")

        if st.button(
            "Ouvrir Dashboard Site",
            use_container_width=True,
            width=300
        ):
            st.session_state["module"] = "SITE"
            st.rerun()


    with col4:

        st.image(
            "assets/battery.png",
            use_container_width=True
        )

        st.subheader("☀️ Batteries")

        if st.button(
            "Ouvrir Dashboard Batteries",
            use_container_width=True,
            width=300
        ):
            st.session_state["module"] = "BATTERY"
            st.rerun()


    with col5:

        st.image(
            "assets/powercore.png",
            use_container_width=True
        )

        st.subheader("☀️ PowerCore")

        if st.button(
            "Ouvrir Dashboard Powercore",
            use_container_width=True,
            width=300
        ):
            st.session_state["module"] = "POWERCORE"
            st.rerun()

    with col6:

        st.image(
            "assets/powercore.png",
            use_container_width=True
        )

        st.subheader("☀️ Grid")

        if st.button(
            "Ouvrir Dashboard Grid",
            use_container_width=True,
            width=300
        ):
            st.session_state["module"] = "GRID"
            st.rerun()





    if "module" in st.session_state:

        if st.session_state["module"] == "SOLAIRE":
            show_solaire()

        elif st.session_state["module"] == "GE":
            show_ge()

        elif st.session_state["module"] == "SITE":
            show_site()
        
        elif st.session_state["module"] == "BATTERY":
            show_batterie()
            
        elif st.session_state["module"] == "POWERCORE":
            show_powercore()

        elif st.session_state["module"] == "GRID":
            show_grid()