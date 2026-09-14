import streamlit as st
import pandas as pd

from modules.solaires.dialog_alert import dialog_alert

from config.database import engine

# =====================================================
# PAGE
# =====================================================

def show():

    st.title("🚨 Gestion des Alertes")

    st.markdown("Liste des sites disposant d'une installation solaire")

    # =====================================================
    # REQUETE
    # =====================================================

    query = """
    SELECT

        s.site_id,
        s.code_site,
        s.site_name,

        t.team_name,

        si.panel_quantity,
        si.panel_power_wc,

        si.ipv_efficiency,

        a.alert_id,
        a.alert_date,
        a.alert_type,
        a.severity,
        a.status,
        a.description

    FROM solar_installations si

    INNER JOIN sites s
        ON si.site_id = s.site_id

    LEFT JOIN teams t
        ON s.team_id = t.team_id

    LEFT JOIN (

        SELECT DISTINCT ON (site_id)

            *

        FROM solar_alerts

        WHERE status='OPEN'

        ORDER BY
            site_id,
            alert_date DESC

    ) a

        ON s.site_id=a.site_id

    ORDER BY
        s.code_site
    """

    df = pd.read_sql(query, engine)

    # =====================================================
    # MISE EN FORME
    # =====================================================

    df["Puissance Totale (Wc)"] = (
        df["panel_quantity"].fillna(0)
        *
        df["panel_power_wc"].fillna(0)
    )

    df["Alerte"] = df["alert_type"].fillna("RAS")

    df["Criticité"] = df["severity"].fillna("-")

    df["Status"] = df["status"].fillna("-")

    # =====================================================
    # TABLEAU
    # =====================================================

# =====================================================
# EN-TETE
# =====================================================

    c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(
        [1.2, 2.5, 1.5, 1.2, 1.2, 1.2, 1.2, 1.2, 2]
    )

    c1.markdown("**Site**")
    c2.markdown("**Nom Site**")
    c3.markdown("**Equipe**")
    c4.markdown("**Panneaux**")
    c5.markdown("**Puissance**")
    c6.markdown("**Criticité**")
    c7.markdown("**Status**")
    c8.markdown("**Alerte**")
    c9.markdown("**Action**")

    st.divider()

# =====================================================
# TABLEAU
# =====================================================

    for _, row in df.iterrows():

        c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(
            [1.2, 2.5, 1.5, 1.2, 1.2, 1.2, 1.2, 1.2, 2]
        )

        c1.write(row["code_site"])
        c2.write(row["site_name"])
        c3.write(row["team_name"])
        c4.write(row["panel_quantity"])
        c5.write(f"{row['Puissance Totale (Wc)']:.0f} W")

        # Couleur Criticité
        severity = str(row["Criticité"]).upper()

        if severity == "CRITICAL":
            c6.error("CRITICAL")

        elif severity == "MAJOR":
            c6.warning("MAJOR")

        elif severity == "MINOR":
            c6.info("MINOR")

        else:
            c6.success("RAS")

        c7.write(row["Status"])
        c8.write(row["Alerte"])

# ==========================================
# BOUTONS
# ==========================================

        if pd.isna(row["alert_id"]):

            if c9.button(
                "➕ Nouvelle",
                key=f"add_{row['site_id']}"
            ):
                dialog_alert(
                    site_id=row["site_id"]
                )

        else:

            colA, colB = c9.columns(2)

            if colA.button(
                "✏️",
                key=f"edit_{row['alert_id']}"
            ):
                dialog_alert(
                    site_id=row["site_id"],
                    alert_id=int(row["alert_id"])
                )

            if colB.button(
                "✅",
                key=f"close_{row['alert_id']}"
            ):

                with engine.begin() as conn:

                    conn.execute(
                        """
                        UPDATE solar_alerts
                        SET status='CLOSED'
                        WHERE alert_id=%s
                        """,
                        (int(row["alert_id"]),)
                    )

                st.success("Alerte clôturée.")

                st.rerun()




