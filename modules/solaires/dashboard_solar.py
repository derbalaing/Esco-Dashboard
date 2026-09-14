import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from config.database import engine
from modules.ui import open_card, close_card
from modules.ui import chart_title
from modules.ui import chart_card
from modules.ui import begin_chart_card
from streamlit_extras.stylable_container import stylable_container
from modules.ui import chart_card
from datetime import date, timedelta
from sqlalchemy import text
from config.database import engine

def show_dashboard():

    st.title("☀️ Dashboard Solaire")



    # ==================================================
    # FILTRE GLOBAL BATCH SOLAIRE
    # ==================================================

    query_batches = """
    SELECT DISTINCT
        COALESCE(NULLIF(TRIM(batch), ''), 'Non défini') AS batch
    FROM solar_installations
    ORDER BY batch
    """

    df_batches = pd.read_sql(query_batches, engine)

    batch_options = ["TOUS"] + df_batches["batch"].dropna().tolist()

    selected_batch = st.sidebar.selectbox(
        "Filtre Batch solaire",
        batch_options,
        index=0,
        key="solar_global_batch_filter"
    )

    selected_batch_param = None

    if selected_batch != "TOUS":
        selected_batch_param = selected_batch



    # ==================================================
    # KPI PRINCIPAUX
    # ==================================================

    query_kpi = """
    WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        COALESCE(SUM(k.actual_production_kwh),0) AS production,
        COALESCE(SUM(k.target_kwh),0) AS target
    FROM solar_kpi_daily k
    LEFT JOIN solar_batch sb
        ON sb.site_id = k.site_id
    WHERE k.kpi_date = (
        SELECT MAX(kpi_date)
        FROM solar_kpi_daily
    )
    AND (
        %(selected_batch)s IS NULL
        OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
    )
    """

    df = pd.read_sql(
        """
        WITH solar_batch AS
        (
            SELECT
                site_id,
                COALESCE(
                    MAX(NULLIF(TRIM(batch), '')),
                    'Non défini'
                ) AS batch
            FROM solar_installations
            GROUP BY site_id
        )

        SELECT
            k.*,
            s.*,
            COALESCE(sb.batch, 'Non défini') AS batch
        FROM solar_kpi_daily k
        JOIN sites s
            ON k.site_id = s.site_id
        LEFT JOIN solar_batch sb
            ON sb.site_id = k.site_id
        WHERE
            (
                %(selected_batch)s IS NULL
                OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
            )
        """,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )

    # Dernière date disponible
    df["Date"] = pd.to_datetime(df["kpi_date"])
    last_day = df["Date"].max()
    st.write(f"Dernière date disponible : {last_day.date()}")
    df_day = df[df["Date"] == last_day]


    sites_ok = len(df_day[df_day["actual_production_kwh"] > 0])

    sites_zero = len(df_day[df_day["actual_production_kwh"] == 0])

    sites_lostcom = len(df_day[df_day["status"] == "LOSTCOM"])

    avg_prod = df[df["actual_production_kwh"] > 0]["actual_production_kwh"].mean()
    

    df_kpi = pd.read_sql(
        query_kpi,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )

    production = float(df_kpi.iloc[0]["production"])
    target = float(df_kpi.iloc[0]["target"])

    performance = 0

    if target > 0:
        performance = production / target * 100

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">☀️ Production Jour</div>
            <div class="kpi-value">{production:,.0f}</div>
            <small>kWh</small>
        </div>
        """, unsafe_allow_html=True)

    with c2:

        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">🎯 Target Jour</div>
            <div class="kpi-value">{target:,.0f}</div>
            <small>kWh</small>
        </div>
        """, unsafe_allow_html=True)
    with c3:

        st.markdown(f"""
        <div class="blue-card">
            <div class="kpi-title">📈 Performance</div>
            <div class="kpi-value">{performance:.1f}</div>
            <small> %</small>
        </div>
        """, unsafe_allow_html=True)
    with c4:

        st.markdown(f"""
        <div class="black-card">
            <div class="kpi-title">📡 Site en lostcom</div>
            <div class="kpi-value">{sites_lostcom:,.0f}</div>
            <small></small>
        </div>
        """, unsafe_allow_html=True)
    with c5:

        st.markdown(f"""
        <div class="production-card">
            <div class="kpi-title">☀️ Sites Producteurs</div>
            <div class="kpi-value">{sites_ok:,.0f}</div>
            <small></small>
        </div>
        """, unsafe_allow_html=True)
    with c6:

        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">❌ Production Nulle</div>
            <div class="kpi-value">{sites_zero:,.0f}</div>
            <small></small>
        </div>
        """, unsafe_allow_html=True)


    st.divider()



    # ==================================================
    # TABLEAU SITES LOSTCOM ET PRODUCTION NULLE
    # ==================================================

    query_sites_alert = """
    WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        s.code_site,
        s.site_name,
        COALESCE(sb.batch, 'Non défini') AS batch,
        k.kpi_date,
        COALESCE(k.actual_production_kwh, 0) AS actual_production_kwh,
        COALESCE(k.target_kwh, 0) AS target_kwh,
        COALESCE(k.variance_kwh, 0) AS variance_kwh,
        COALESCE(k.status, '-') AS status,

        CASE
            WHEN COALESCE(UPPER(TRIM(k.status)), '') = 'LOSTCOM'
            THEN 'LOSTCOM'

            WHEN COALESCE(k.actual_production_kwh, 0) = 0
                AND COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
            THEN 'PRODUCTION NULLE'

            ELSE 'AUTRE'
        END AS categorie

    FROM solar_kpi_daily k

    INNER JOIN sites s
        ON s.site_id = k.site_id

    LEFT JOIN solar_batch sb
        ON sb.site_id = k.site_id

    WHERE k.kpi_date = %(last_day)s
    AND (
        %(selected_batch)s IS NULL
        OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
        )
    AND (
            COALESCE(UPPER(TRIM(k.status)), '') = 'LOSTCOM'

            OR
            (
                COALESCE(k.actual_production_kwh, 0) = 0
                AND COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
            )
    )

    ORDER BY
        categorie,
        sb.batch,
        s.code_site
    """

    df_sites_alert = pd.read_sql(
        query_sites_alert,
        engine,
        params={
            "last_day": last_day.date(),
            "selected_batch": selected_batch_param
        }
    )

    with stylable_container(
        key="table_lostcom_zero_prod_card",
        css_styles="""
        {
            background-color: white;
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,.12);
            border-top: 6px solid #dc2626;
            margin-bottom:20px;
        }
        """
    ):
        st.subheader("📋 Sites en LOSTCOM et Production Nulle")
        st.caption(f"Dernière date disponible : {last_day.date()}")



        if not df_sites_alert.empty:

            df_sites_alert["batch"] = (
                df_sites_alert["batch"]
                .fillna("Non défini")
                .astype(str)
                .str.strip()
            )


        if df_sites_alert.empty:

            st.success("Aucun site en LOSTCOM ou en production nulle.")

        else:

            df_lostcom = df_sites_alert[
                df_sites_alert["categorie"] == "LOSTCOM"
            ].copy()

            df_zero = df_sites_alert[
                df_sites_alert["categorie"] == "PRODUCTION NULLE"
            ].copy()

            c1, c2 = st.columns(2)

            with c1:
                st.metric(
                    "Sites LOSTCOM",
                    len(df_lostcom)
                )

            with c2:
                st.metric(
                    "Production nulle",
                    len(df_zero)
                )

            tab1, tab2, tab3 = st.tabs(
                [
                    "📡 LOSTCOM",
                    "❌ Production nulle",
                    "📋 Tous"
                ]
            )

            with tab1:

                st.dataframe(
                    df_lostcom[
                        [
                            "code_site",
                            "site_name",
                            "batch",
                            "kpi_date",
                            "status",
                            "actual_production_kwh",
                            "target_kwh",
                            "variance_kwh",
                        ]
                    ],
                    use_container_width=True,
                    height=350
                )

            with tab2:

                st.dataframe(
                    df_zero[
                        [
                            "code_site",
                            "site_name",
                            "batch",
                            "kpi_date",
                            "status",
                            "actual_production_kwh",
                            "target_kwh",
                            "variance_kwh",
                        ]
                    ],
                    use_container_width=True,
                    height=350
                )

            with tab3:

                st.dataframe(
                    df_sites_alert[
                        [
                            "categorie",
                            "code_site",
                            "site_name",
                            "batch",
                            "kpi_date",
                            "status",
                            "actual_production_kwh",
                            "target_kwh",
                            "variance_kwh",
                        ]
                    ],
                    use_container_width=True,
                    height=450
                )

    st.divider()


    # ==================================================
    # HISTOGRAMME LOSTCOM / PRODUCTION NULLE PAR EQUIPE
    # ==================================================

    query_alert_team = """
        WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        COALESCE(t.team_name, 'Non affectée') AS team_name,

        COUNT(
            DISTINCT CASE
                WHEN COALESCE(UPPER(TRIM(k.status)), '') = 'LOSTCOM'
                THEN k.site_id
            END
        ) AS sites_lostcom,

        COUNT(
            DISTINCT CASE
                WHEN COALESCE(k.actual_production_kwh, 0) = 0
                    AND COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
                THEN k.site_id
            END
        ) AS sites_production_nulle

    FROM solar_kpi_daily k


    LEFT JOIN solar_batch sb
    ON sb.site_id = k.site_id

    INNER JOIN sites s
        ON s.site_id = k.site_id

    LEFT JOIN teams t
        ON t.team_id = s.team_id

    WHERE k.kpi_date = %(last_day)s
    AND (
        %(selected_batch)s IS NULL
        OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
        )
    GROUP BY
        COALESCE(t.team_name, 'Non affectée')

    HAVING
        COUNT(
            DISTINCT CASE
                WHEN COALESCE(UPPER(TRIM(k.status)), '') = 'LOSTCOM'
                THEN k.site_id
            END
        ) > 0

        OR

        COUNT(
            DISTINCT CASE
                WHEN COALESCE(k.actual_production_kwh, 0) = 0
                    AND COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
                THEN k.site_id
            END
        ) > 0

    ORDER BY
        sites_lostcom DESC,
        sites_production_nulle DESC,
        team_name
    """

    df_alert_team = pd.read_sql(
        query_alert_team,
        engine,
        params={
            "last_day": last_day.date(),
            "selected_batch": selected_batch_param
        }
    )

    with stylable_container(
        key="hist_lostcom_zero_by_team_card",
        css_styles="""
        {
            background-color: white;
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,.12);
            border-top: 6px solid #dc2626;
            margin-bottom:20px;
        }
        """
    ):
        st.subheader("📊 LOSTCOM et Production nulle par équipe")
        st.caption(f"Analyse par équipe - Date : {last_day.date()}")

        if df_alert_team.empty:

            st.success("Aucun site en LOSTCOM ou en production nulle par équipe.")

        else:

            fig_team_alert = go.Figure()

            fig_team_alert.add_trace(
                go.Bar(
                    x=df_alert_team["team_name"],
                    y=df_alert_team["sites_lostcom"],
                    name="LOSTCOM",
                    text=df_alert_team["sites_lostcom"],
                    textposition="outside"
                )
            )

            fig_team_alert.add_trace(
                go.Bar(
                    x=df_alert_team["team_name"],
                    y=df_alert_team["sites_production_nulle"],
                    name="Production nulle",
                    text=df_alert_team["sites_production_nulle"],
                    textposition="outside"
                )
            )

            fig_team_alert.update_layout(
                barmode="group",
                height=500,
                title="Sites LOSTCOM et Production nulle par équipe",
                xaxis_title="Équipe",
                yaxis_title="Nombre de sites",
                legend=dict(
                    orientation="h"
                ),
                xaxis=dict(
                    tickangle=-45
                )
            )

            st.plotly_chart(
                fig_team_alert,
                use_container_width=True,
                key="chart_lostcom_zero_by_team"
            )

            st.dataframe(
                df_alert_team,
                use_container_width=True,
                height=300
            )

    st.divider()

    # ==================================================
    # PRODUCTION VS TARGET JOURNALIER
    # ==================================================
    
    query_chart = """
    WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        k.kpi_date,
        SUM(k.actual_production_kwh) AS production,
        SUM(k.target_kwh) AS target
    FROM solar_kpi_daily k

    LEFT JOIN solar_batch sb
        ON sb.site_id = k.site_id

    WHERE
        (
            %(selected_batch)s IS NULL
            OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
        )

    GROUP BY
        k.kpi_date

    ORDER BY
        k.kpi_date
    """

    df_chart = pd.read_sql(
        query_chart,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )


    st.write(
        "Nombre de jours :",
        len(df_chart)
    )

    if len(df_chart) > 0:

        df_chart["kpi_date"] = pd.to_datetime(
            df_chart["kpi_date"]
        )

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=df_chart["kpi_date"],
                y=df_chart["production"],
                mode="lines+markers",
                name="Production Réelle",
                line=dict(
                    color="black",
                    width=1
                    )
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df_chart["kpi_date"],
                y=df_chart["target"],
                mode="lines",
                name="Production Cible",
                line=dict(
                    color="orange",
                    width=2
                )
            )
        )

        fig.update_layout(
            height=500,
            title="Production Journalière vs Target"
        )

        with stylable_container(
        key="prod_card",
        css_styles="""
        {
            background-color: white;
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,.12);
            border-top: 6px solid #e09800;
            margin-bottom:20px;
        }
        """
        ):
            st.subheader("📊 Production Réelle vs Target")
            st.caption("Écart entre Production réelle et Target.   ||   Nombre de jours : len(df_chart)")

            st.plotly_chart(fig, use_container_width=True)

    else:

        st.warning(
            "Aucune donnée trouvée."
        )

    st.divider()

    # ==================================================
    # GAP MENSUEL
    # ==================================================


    query_gap = """
    WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        DATE_TRUNC('month', k.kpi_date) AS month,

        SUM(k.actual_production_kwh) AS production,

        SUM(k.target_kwh) AS target,

        SUM(k.actual_production_kwh) - SUM(k.target_kwh) AS gap

    FROM solar_kpi_daily k

    LEFT JOIN solar_batch sb
        ON sb.site_id = k.site_id

    WHERE
        (
            %(selected_batch)s IS NULL
            OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
        )

    GROUP BY
        DATE_TRUNC('month', k.kpi_date)

    ORDER BY
        month
    """

    df_gap = pd.read_sql(
        query_gap,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )

    if len(df_gap) > 0:

        fig_gap = go.Figure()

        fig_gap.add_trace(
            go.Bar(
                x=df_gap["month"],
                y=df_gap["gap"],
                name="Gap"
            )
        )

        fig_gap.update_layout(
            height=500,
            title="Gap Mensuel (Production - Target)"
        )

        with stylable_container(
        key="gaps_card",
        css_styles="""
        {
            background-color: white;
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,.12);
            border-top: 6px solid #e09800;
            margin-bottom:20px;
        }
        """
        ):
            st.subheader("📊 Gap Mensuel")
            st.caption("Écart entre Production réelle et Target  ||  Nombre de mois : len(df_gap)")

            st.plotly_chart(fig_gap, use_container_width=True)


    else:

        st.warning(
            "Aucune donnée de gap."
        )

    st.divider()

    # ==================================================
    # PRODUCTION / TARGET / GAP
    # ==================================================


    if len(df_gap) > 0:

        fig_month = go.Figure()

        fig_month.add_trace(
            go.Bar(
                x=df_gap["month"],
                y=df_gap["production"],
                name="Production"
            )
        )

        fig_month.add_trace(
            go.Bar(
                x=df_gap["month"],
                y=df_gap["target"],
                name="Target"
            )
        )

        fig_month.add_trace(
            go.Scatter(
                x=df_gap["month"],
                y=df_gap["gap"],
                mode="lines+markers",
                name="Gap"
            )
        )

        fig_month.update_layout(
            barmode="group",
            height=600
        )

        with stylable_container(
        key="gap_month_card",
        css_styles="""
        {
            background-color: white;
            border-radius: 18px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,.12);
            border-top: 6px solid #e09800;
            margin-bottom:20px;
        }
        """
        ):
            st.subheader("📊 Production / Target / Gap Mensuel")
            st.caption("Écart entre Production réelle et Target")

            st.plotly_chart(fig_month, use_container_width=True)
        

    st.divider()

    # ==================================================
    # TABLEAU DE CONTROLE
    # ==================================================


    with stylable_container(
    key="df_chart",
    css_styles="""
    {
        background-color: white;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,.12);
        border-top: 6px solid #e09800;
        margin-bottom:20px;
    }
    """
    ):
        st.subheader("📊 Contrôle données")
        st.caption("Écart entre Production réelle et Target")

        st.dataframe(
        df_chart.tail(20),
        use_container_width=True
        )
 




    query_gap = """
    WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        k.kpi_date,
        SUM(k.variance_kwh) AS gap

    FROM solar_kpi_daily k

    LEFT JOIN solar_batch sb
        ON sb.site_id = k.site_id

    WHERE k.kpi_date >= CURRENT_DATE - INTERVAL '30 days'

    AND (
        %(selected_batch)s IS NULL
        OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
    )

    GROUP BY
        k.kpi_date

    ORDER BY
        k.kpi_date
    """

    df_gap = pd.read_sql(
        query_gap,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )

    df_gap["kpi_date"] = pd.to_datetime(df_gap["kpi_date"])


    fig_gap = go.Figure()

    fig_gap.add_trace(

        go.Bar(

            x=df_gap["kpi_date"],

            y=df_gap["gap"],

            marker_color=[
                "green" if x >= 0 else "red"
                for x in df_gap["gap"]
            ],

            name="Gap"
        )
    )

    fig_gap.update_layout(

       
        xaxis_title="Date",

        yaxis_title="Gap (kWh)",

        height=450
    )

    with stylable_container(
    key="fig_gap_card",
    css_styles="""
    {
        background-color: white;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,.12);
        border-top: 6px solid #e09800;
        margin-bottom:20px;
    }
    """
    ):
        st.subheader("📊 Gap global - 30 derniers jours")
        st.caption("Écart entre Production réelle et Target")

        st.plotly_chart(fig_gap, use_container_width=True)
 





    with stylable_container(
    key="gap_cardt",
    css_styles="""
    {
        background-color: white;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,.12);
        border-top: 6px solid #3498db;
        margin-bottom:20px;
    }
    """
    ):


        date_fin = st.date_input(
            "Date de fin de l'analyse",
            value=date.today(),
            max_value=date.today()
        )

        date_debut = date_fin - timedelta(days=29)

    



        query_gap_site = """
        WITH solar_batch AS
        (
            SELECT
                site_id,
                COALESCE(
                    MAX(NULLIF(TRIM(batch), '')),
                    'Non défini'
                ) AS batch
            FROM solar_installations
            GROUP BY site_id
        )

        SELECT

            s.code_site,

            SUM(k.variance_kwh) AS gap

        FROM solar_kpi_daily k
        LEFT JOIN solar_batch sb
            ON sb.site_id = k.site_id
        JOIN sites s
            ON k.site_id = s.site_id

        WHERE k.kpi_date BETWEEN %(date_debut)s AND %(date_fin)s
        AND (
            %(selected_batch)s IS NULL
            OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
        )
        GROUP BY
            s.code_site

        ORDER BY
            gap ASC
        """



        df_gap_site = pd.read_sql(
            query_gap_site,
            engine,
            params={
            "date_debut": date_debut,
            "date_fin": date_fin,
            "selected_batch": selected_batch_param
            }
        )

        fig = go.Figure()

        fig.add_trace(

        go.Bar(

            y=df_gap_site["code_site"],

            x=df_gap_site["gap"],

            orientation="h",

            marker_color=[
                "red" if x < 0 else "green"
                for x in df_gap_site["gap"]
            ],

            text=df_gap_site["gap"].round(1),

            textposition="outside"
            )
         )

        fig.update_layout(

        height=max(600, len(df_gap_site) * 20),

        xaxis_title="Gap (kWh)",

        yaxis_title="Site",

        title=f"Gap cumulé par site ({date_debut.strftime('%d/%m/%Y')} → {date_fin.strftime('%d/%m/%Y')})",

        yaxis=dict(autorange="reversed")
        )


        st.caption(f"Période analysée : {date_debut.strftime('%d/%m/%Y')} → {date_fin.strftime('%d/%m/%Y')}" )
        st.subheader("📉 Gap cumulé par site - 30 derniers jours")
     

        st.plotly_chart(fig, use_container_width=True)




        query_gap_sites = """
        WITH solar_batch AS
        (
            SELECT
                site_id,
                COALESCE(
                    MAX(NULLIF(TRIM(batch), '')),
                    'Non défini'
                ) AS batch
            FROM solar_installations
            GROUP BY site_id
        )

        SELECT
            s.site_id,
            s.code_site,
            s.site_name,

            ROUND(
                SUM(k.variance_kwh),
                2
            ) AS gap_30j,

            ROUND(
                SUM(
                    CASE
                        WHEN k.kpi_date >= CURRENT_DATE - INTERVAL '4 days'
                        THEN k.variance_kwh
                        ELSE 0
                    END
                ),
                2
            ) AS gap_5j,

            ROUND(
                SUM(
                    CASE
                        WHEN k.kpi_date < CURRENT_DATE - INTERVAL '4 days'
                        THEN k.variance_kwh
                        ELSE 0
                    END
                ),
                2
            ) AS gap_25j

        FROM solar_kpi_daily k
        LEFT JOIN solar_batch sb
            ON sb.site_id = k.site_id
        INNER JOIN sites s
            ON s.site_id = k.site_id

        WHERE k.kpi_date BETWEEN
            CURRENT_DATE - INTERVAL '29 days'
            AND CURRENT_DATE
        AND (
            %(selected_batch)s IS NULL
            OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
        )
        GROUP BY
            s.site_id,
            s.code_site,
            s.site_name

        ORDER BY
            gap_5j ASC;
    """

    df_gap_sites = pd.read_sql(
        query_gap_sites,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )


    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_gap_sites["code_site"],
            y=df_gap_sites["gap_25j"],
            name="J-30 à J-6",
            marker_color="steelblue"
        )
    )

    fig.add_trace(
        go.Bar(
            x=df_gap_sites["code_site"],
            y=df_gap_sites["gap_5j"],
            name="5 derniers jours",
            marker_color="crimson"
        )
    )

    fig.update_layout(
        height=max(600, len(df_gap_sites) * 20),

        xaxis_title="Gap (kWh)",

        yaxis_title="Site",

        title=f"Gap cumulé par site ",

        yaxis=dict(autorange="reversed")
    )




    with stylable_container(
    key="gap_card",
    css_styles="""
    {
        background-color: white;
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,.12);
        border-top: 6px solid #e09800;
        margin-bottom:20px;
    }
    """
    ):
        st.subheader("📊 Gap global - 30 derniers jours")
        st.caption("Écart entre Production réelle et Target")

        st.plotly_chart(fig, use_container_width=True)






    # ==================================================
    # PRODUCTION / TARGET / GAP MENSUEL - SITES VISIBLES
    # ==================================================

    query_month_visible = """
    WITH solar_batch AS
    (
        SELECT
            site_id,
            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch
        FROM solar_installations
        GROUP BY site_id
    )

    SELECT
        DATE_TRUNC('month', k.kpi_date) AS month,

        SUM(k.actual_production_kwh) AS production,

        SUM(k.target_kwh) AS target,

        SUM(k.actual_production_kwh) - SUM(k.target_kwh) AS gap

    FROM solar_kpi_daily k

    LEFT JOIN solar_batch sb
        ON sb.site_id = k.site_id

    WHERE COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'

    AND (
        %(selected_batch)s IS NULL
        OR COALESCE(sb.batch, 'Non défini') = %(selected_batch)s
    )

    GROUP BY
        DATE_TRUNC('month', k.kpi_date)

    ORDER BY
        month
    """

    df_month_visible = pd.read_sql(
        query_month_visible,
        engine,
        params={
            "selected_batch": selected_batch_param
        }
    )

    if len(df_month_visible) > 0:

        df_month_visible["month"] = pd.to_datetime(
            df_month_visible["month"]
        )

        fig_month_visible = go.Figure()

        fig_month_visible.add_trace(
            go.Bar(
                x=df_month_visible["month"],
                y=df_month_visible["production"],
                name="Production visible"
            )
        )

        fig_month_visible.add_trace(
            go.Bar(
                x=df_month_visible["month"],
                y=df_month_visible["target"],
                name="Target visible"
            )
        )

        fig_month_visible.add_trace(
            go.Scatter(
                x=df_month_visible["month"],
                y=df_month_visible["gap"],
                mode="lines+markers",
                name="Gap visible",
                yaxis="y2"
            )
        )

        fig_month_visible.update_layout(
            barmode="group",
            height=600,
            title="Production / Target / Gap Mensuel - Sites visibles uniquement",
            xaxis_title="Mois",
            yaxis=dict(
                title="Production / Target (kWh)"
            ),
            yaxis2=dict(
                title="Gap (kWh)",
                overlaying="y",
                side="right"
            ),
            legend=dict(
                orientation="h"
            )
        )

        with stylable_container(
            key="month_visible_card_without_lostcom",
            css_styles="""
            {
                background-color: white;
                border-radius: 18px;
                padding: 20px;
                box-shadow: 0 4px 12px rgba(0,0,0,.12);
                border-top: 6px solid #16a34a;
                margin-bottom:20px;
            }
            """
        ):
            st.subheader("📊 Production / Target / Gap Mensuel - Sites visibles")
            st.caption("Les sites en LOSTCOM sont exclus du calcul.")

            st.plotly_chart(
                fig_month_visible,
                use_container_width=True,
                key="chart_month_visible_without_lostcom"
            )

    else:

        st.warning(
            "Aucune donnée trouvée pour les sites visibles."
        )

    st.divider()






    @st.cache_data(ttl=300)
    def load_solar_monthly_status_summary():

            query = text("""
            SELECT
                solar_month,
                total_solar_sites,
                lostcom_sites,
                zero_prod_sites,
                degraded_sites,
                ok_sites,
                actual_production_kwh,
                target_calculated_kwh,
                target_80_kwh,
                gap_vs_target_80_kwh,
                performance_vs_target_pct,
                performance_vs_target_80_pct
            FROM v_solar_monthly_status_summary
            ORDER BY solar_month
            """)

            df = pd.read_sql(query, engine)

            if df.empty:
                return df

            df["solar_month"] = pd.to_datetime(
                df["solar_month"],
                errors="coerce"
            ).dt.date

            numeric_cols = [
                "total_solar_sites",
                "lostcom_sites",
                "zero_prod_sites",
                "degraded_sites",
                "ok_sites",
                "actual_production_kwh",
                "target_calculated_kwh",
                "target_80_kwh",
                "gap_vs_target_80_kwh",
                "performance_vs_target_pct",
                "performance_vs_target_80_pct",
            ]


            for col in numeric_cols:
                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce"
                ).fillna(0)

            if "lostcom_pct" not in df.columns:

                df["lostcom_pct"] = 0.0

                mask_total_sites = df["total_solar_sites"] > 0

                df.loc[mask_total_sites, "lostcom_pct"] = (
                    df.loc[mask_total_sites, "lostcom_sites"]
                    /
                    df.loc[mask_total_sites, "total_solar_sites"]
                    * 100
                )

            return df


    st.divider()
    st.subheader("📅 Récap mensuel production solaire vs target")

    df_monthly_solar = load_solar_monthly_status_summary()

    if df_monthly_solar.empty:

        st.info("Aucune donnée mensuelle solaire disponible.")

    else:

        latest_month = df_monthly_solar.iloc[-1]

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric(
                "Production réelle dernier mois",
                f"{latest_month['actual_production_kwh']:.1f} kWh"
            )

        with c2:
            st.metric(
                "Target 80% dernier mois",
                f"{latest_month['target_80_kwh']:.1f} kWh"
            )

        with c3:
            st.metric(
                "Performance vs target",
                f"{latest_month['performance_vs_target_pct']:.1f} %"
            )

        with c4:
            st.metric(
                "Sites OK",
                f"{latest_month['ok_sites']:.0f}"
            )

        display_cols = [
            "solar_month",
            "total_solar_sites",
            "lostcom_sites",
            "lostcom_pct",
            "zero_prod_sites",
            "degraded_sites",
            "ok_sites",
            "actual_production_kwh",
            "target_calculated_kwh",
            "target_70_kwh",
            "gap_vs_target_80_kwh",
            "performance_vs_target_pct",
            "performance_vs_target_80_pct",
        ]

        display_cols = [
            col for col in display_cols
            if col in df_monthly_solar.columns
        ]

        st.dataframe(
            df_monthly_solar[display_cols],
            use_container_width=True,
            hide_index=True
        )

        st.dataframe(
            df_monthly_solar[display_cols],
            use_container_width=True,
            hide_index=True
        )

        fig_prod = px.line(
            df_monthly_solar,
            x="solar_month",
            y=[
                "actual_production_kwh",
                "target_calculated_kwh",
                "target_80_kwh",
            ],
            markers=True,
            title="Évolution mensuelle production solaire vs target"
        )

        fig_prod.update_layout(
            height=450,
            xaxis_title="Mois",
            yaxis_title="Énergie solaire (kWh)",
            legend_title="Indicateur"
        )

        st.plotly_chart(
            fig_prod,
            use_container_width=True,
            key="solar_monthly_production_vs_target"
        )