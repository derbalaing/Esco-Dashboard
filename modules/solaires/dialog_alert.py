from sqlalchemy import text
from config.database import engine
import streamlit as st

@st.dialog("Gestion de l'alerte")
def dialog_alert(site_id, alert_id=None):

    if alert_id is None:

        st.write("Site :", site_id)

        alert_type = st.selectbox(
            "Type",
            [
                "Production dégradé",
                "Production nulle",
                "Visibilité",
                "Information",
                "Chargeur Solaire"
            ]
        )

        severity = st.selectbox(
            "Criticité",
            [
                "CRITICAL",
                "MAJOR",
                "MINOR",
                "INFO"
            ]
        )

        valeur = st.number_input(
            "Valeur",
            value=0.0
        )

        description = st.text_area(
            "Description"
        )

        status = st.selectbox(
            "Status",
            [
                "OPEN",
                "STANDBY",
                "CLOSED"
            ]
        )

        col1, col2 = st.columns(2)

        with col1:



            if st.button("💾 Enregistrer"):

                sql = text("""
                    INSERT INTO solar_alerts
                    (
                        site_id,
                        alert_date,
                        alert_type,
                        severity,
                        value,
                        description,
                        status,
                        created_at
                    )

                    VALUES
                    (
                        :site_id,
                        CURRENT_DATE,
                        :alert_type,
                        :severity,
                        :value,
                        :description,
                        :status,
                        NOW()
                    )
                """)

                try:

                    with engine.begin() as conn:

                        conn.execute(
                            sql,
                            {
                                "site_id": site_id,
                                "alert_type": alert_type,
                                "severity": severity,
                                "value": valeur,
                                "description": description,
                                "status": status
                            }
                        )

                    st.success("✅ Alerte enregistrée avec succès.")

                    st.rerun()

                except Exception as e:

                    st.error(e)

        with col2:

            if st.button("❌ Annuler"):

                st.rerun()

   

         
        # ==================================================
        # CHARGEMENT DES DONNEES
        # ==================================================


    else:

            sql = text("""
                SELECT
                    alert_type,
                    severity,
                    value,
                    description,
                    status
                FROM solar_alerts
                WHERE alert_id = :alert_id
            """)

            with engine.begin() as conn:

                row = conn.execute(
                    sql,
                    {"alert_id": alert_id}
                ).fetchone()

            if row is None:

                st.error("Alerte introuvable.")
                return

            alert_type_default = row.alert_type
            severity_default = row.severity.strip()
            value_default = float(row.value or 0)
            description_default = row.description or ""
            status_default = row.status