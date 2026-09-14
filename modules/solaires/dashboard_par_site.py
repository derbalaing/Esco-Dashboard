import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config.database import engine


def show():

    st.title("☀️ Analyse Solaire par Site")

    # ==================================================
    # LISTE DES SITES
    # ==================================================

    sites = pd.read_sql(
        """
        SELECT
            s.site_id,
            s.code_site,
            s.site_name
        
        FROM sites s

        JOIN solar_installations si
            ON s.site_id = si.site_id
        ORDER BY s.code_site
        """,
        engine
    )

    site_selected = st.selectbox(
        "Choisir un site",
        sites["code_site"]
    )

    site_id = sites.loc[
        sites["code_site"] == site_selected,
        "site_id"
    ].iloc[0]

    # ==================================================
    # INFOS SITE
    # ==================================================

    query_site = f"""
    SELECT
        s.code_site,
        s.site_name,
        si.panel_type,
        si.panel_power_wc,
        si.panel_quantity,
        si.ipv_efficiency

    FROM sites s

    LEFT JOIN solar_installations si
        ON s.site_id = si.site_id

    WHERE s.site_id = {site_id}
    """

    df_site = pd.read_sql(
        query_site,
        engine
    )

    if not df_site.empty:

        row = df_site.iloc[0]

        c1, c2, c3, c4 = st.columns(4)
    if row['ipv_efficiency'] :
                  ipv_effeciency100 = float(row['ipv_efficiency'])*100
    else:
                 ipv_effeciency100 = "NaN"    

    with c1:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">Site</div>
            <div class="kpi-value">{ row["code_site"]}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">Puissance panneau</div>
            <div class="kpi-value">{ row['panel_power_wc']}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">Panneaux</div>
            <div class="kpi-value">{ row["panel_quantity"]}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">IPV Efficiency (%) </div>
            <div class="kpi-value">{ipv_effeciency100}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ==================================================
    # KPI SITE
    # ==================================================

    query_kpi = f"""
    SELECT
        SUM(actual_production_kwh) AS production,
        SUM(target_kwh) AS target

    FROM solar_kpi_daily

    WHERE site_id = {site_id}
    """

    df_kpi = pd.read_sql(
        query_kpi,
        engine
    )

    production = float(df_kpi.iloc[0]["production"] or 0)
    target = float(df_kpi.iloc[0]["target"] or 0)

    performance = 0

    if target > 0:
        performance = (production / target )* 100

    c1, c2, c3 = st.columns(3)

    with c1:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">Production Totale</div>
            <div class="kpi-value">{ production:,.0f}</div>
            <div>Kwh</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
                st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">Target Totale</div>
            <div class="kpi-value">{ target:,.0f}</div>
            <div>Kwh</div>
        </div>
        """, unsafe_allow_html=True)
                
    with c3:     
                st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">Performance</div>
            <div class="kpi-value">{ performance:.1f}</div>
            <div>%</div>
        </div>
        """, unsafe_allow_html=True)
    st.divider()
    # ==================================================
    # ALERTES
    # ==================================================

    st.subheader("🚨 Alertes")

    query_alerts = f"""
    SELECT
        alert_date,
        alert_type,
        severity,
        status,
        description

    FROM solar_alerts

    WHERE site_id = {site_id}

    ORDER BY alert_date DESC
    """

    df_alerts = pd.read_sql(query_alerts, engine)

    if df_alerts.empty:

        st.success("Aucune alerte")

    else:

        for _, row in df_alerts.iterrows():

            severity = str(row["severity"]).strip().upper()
            status = str(row["status"]).strip().upper()

            message = f"""
    📅 Date : {row['alert_date']}

    📌 Type : {row['alert_type']}

    📍 Status : {status}

    📝 {row['description']}
    """

            if severity == "CRITICAL":

                st.error(message)

            elif severity == "MAJOR":

                st.warning(message)

            elif severity == "MINOR":

                st.info(message)

            else:

                st.success(message)

    # ==================================================
    # COURBE JOURNALIERE
    # ==================================================

    query_chart = f"""
    SELECT

        kpi_date,
        actual_production_kwh,
        target_kwh,
        variance_kwh,
        status

    FROM solar_kpi_daily

    WHERE site_id = {site_id}

    ORDER BY kpi_date
    """

    df = pd.read_sql(
        query_chart,
        engine
    )

    if not df.empty:

        df["kpi_date"] = pd.to_datetime(
            df["kpi_date"]
        )

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=df["kpi_date"],
                y=df["actual_production_kwh"],
                name="Production Réelle"
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["kpi_date"],
                y=df["target_kwh"],
                name="Target"
            )
        )

        fig.update_layout(
            title=f"{site_selected} - Production vs Target",
            height=500
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        st.divider()

        # ==================================================
        # GAP
        # ==================================================

        fig_gap = go.Figure()

        fig_gap.add_trace(
            go.Bar(
                x=df["kpi_date"],
                y=df["variance_kwh"],
                name="Gap"
            )
        )

        fig_gap.update_layout(
            title="Gap Journalier",
            height=500
        )

        st.plotly_chart(
            fig_gap,
            use_container_width=True
        )

        st.divider()

        # ==================================================
        # LOSTCOM
        # ==================================================

        st.subheader(
            "Historique LostCom"
        )

        lostcom = df[
            df["status"] == "LOSTCOM"
        ]

        st.dataframe(
            lostcom,
            use_container_width=True
        )

        st.divider()

        # ==================================================
        # LOW PRODUCTION
        # ==================================================

        st.subheader(
            "Historique Faible Production"
        )

        low_prod = df[
            df["status"] == "LOW_PRODUCTION"
        ]

        st.dataframe(
            low_prod,
            use_container_width=True
        )