import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from datetime import date

from config.database import engine


# ==================================================
# LECTURE SQL SECURISEE
# ==================================================

def read_sql(query, params=None):
    with engine.connect() as conn:
        return pd.read_sql(
            text(query),
            conn,
            params=params or {}
        )


# ==================================================
# LISTE DES BATCHS
# ==================================================

@st.cache_data(ttl=300)
def load_batches():

    query = """
    SELECT DISTINCT
        COALESCE(NULLIF(TRIM(batch), ''), 'Non défini') AS batch
    FROM solar_installations
    ORDER BY batch
    """

    return read_sql(query)


# ==================================================
# RESUME SITES SOLAIRES
# ==================================================

@st.cache_data(ttl=300)
def load_solar_sites_summary(selected_batch=None):

    query = """
    WITH last_day AS
    (
        SELECT
            MAX(kpi_date)::date AS max_date
        FROM solar_kpi_daily
    ),

    solar_installation_clean AS
    (
        SELECT
            site_id,

            COALESCE(
                MAX(NULLIF(TRIM(batch), '')),
                'Non défini'
            ) AS batch,
            MIN(installation_date)::date AS installation_date,

            COALESCE(
                MAX(NULLIF(TRIM(panel_type), '')),
                'Non défini'
            ) AS panel_type,

            SUM(COALESCE(panel_quantity, 0)) AS panel_quantity,

            SUM(
                COALESCE(
                    NULLIF(total_installed_power_wc, 0),
                    NULLIF(panel_power_wc, 0) * NULLIF(panel_quantity, 0),
                    0
                )
            ) / 1000.0 AS installed_kwc

        FROM solar_installations

        GROUP BY
            site_id
    ),

    production_all AS
    (
        SELECT
            k.site_id,

            SUM(COALESCE(k.actual_production_kwh, 0)) AS production_total_kwh,

            SUM(COALESCE(k.target_kwh, 0)) AS target_total_kwh,

            COUNT(DISTINCT k.kpi_date) AS total_days_with_kpi,

            COUNT(
                DISTINCT CASE
                    WHEN COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
                    AND COALESCE(k.actual_production_kwh, 0) > 0
                    THEN k.kpi_date
                END
            ) AS production_days_total,

            COUNT(
                DISTINCT CASE
                    WHEN COALESCE(UPPER(TRIM(k.status)), '') = 'LOSTCOM'
                    THEN k.kpi_date
                END
            ) AS lostcom_days_total,

            COUNT(
                DISTINCT CASE
                    WHEN COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
                    AND COALESCE(k.target_kwh, 0) > 0
                    AND COALESCE(k.actual_production_kwh, 0) < COALESCE(k.target_kwh, 0) * 0.70
                    THEN k.kpi_date
                END
            ) AS degraded_days_total

        FROM solar_kpi_daily k

        INNER JOIN solar_installation_clean si
            ON si.site_id = k.site_id

        WHERE
            (
                si.installation_date IS NULL
                OR k.kpi_date >= si.installation_date
            )

        GROUP BY
            k.site_id
    ),
    latest_alert AS
    (
        SELECT DISTINCT ON (site_id)
            site_id,
            alert_date,
            alert_type,
            severity,
            value AS latest_alert_value,
            description AS latest_alert_description,
            status AS latest_alert_status,
            created_at AS latest_alert_created_at
        FROM solar_alerts
        WHERE site_id IS NOT NULL
        ORDER BY
            site_id,
            alert_date DESC NULLS LAST,
            created_at DESC NULLS LAST,
            alert_id DESC
    ),
    production_10d AS
    (
        SELECT
            k.site_id,

            SUM(COALESCE(k.actual_production_kwh, 0)) AS production_10j_kwh,

            SUM(COALESCE(k.target_kwh, 0)) AS target_10j_kwh,

            COUNT(DISTINCT k.kpi_date) AS days_10j_with_kpi,

            COUNT(
                DISTINCT CASE
                    WHEN COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
                     AND COALESCE(k.actual_production_kwh, 0) > 0
                    THEN k.kpi_date
                END
            ) AS production_days_10j,

            COUNT(
                DISTINCT CASE
                    WHEN COALESCE(UPPER(TRIM(k.status)), '') = 'LOSTCOM'
                    THEN k.kpi_date
                END
            ) AS lostcom_days_10j,

            COUNT(
                DISTINCT CASE
                    WHEN COALESCE(UPPER(TRIM(k.status)), '') <> 'LOSTCOM'
                     AND COALESCE(k.target_kwh, 0) > 0
                     AND COALESCE(k.actual_production_kwh, 0) < COALESCE(k.target_kwh, 0) * 0.70
                    THEN k.kpi_date
                END
            ) AS degraded_days_10j

        FROM solar_kpi_daily k

        CROSS JOIN last_day ld

        WHERE k.kpi_date >= ld.max_date - INTERVAL '9 days'
          AND k.kpi_date <= ld.max_date

        GROUP BY
            k.site_id
    )

    SELECT
        s.site_id,
        s.code_site,
        s.site_name,
        COALESCE(t.team_name, 'Non affectée') AS team_name,
        COALESCE(s.typologie_fms, 'Non défini') AS typologie_fms,

        si.installation_date,
        COALESCE(si.batch, 'Non défini') AS batch,
        COALESCE(si.panel_type, 'Non défini') AS panel_type,
        COALESCE(si.panel_quantity, 0) AS panel_quantity,
        COALESCE(si.installed_kwc, 0) AS installed_kwc,

        COALESCE(pa.target_total_kwh, 0) AS target_total_kwh,
        COALESCE(pa.production_total_kwh, 0) AS production_total_kwh,
        COALESCE(pa.total_days_with_kpi, 0) AS total_days_with_kpi,
        COALESCE(pa.production_days_total, 0) AS production_days_total,
        COALESCE(pa.lostcom_days_total, 0) AS lostcom_days_total,
        COALESCE(pa.degraded_days_total, 0) AS degraded_days_total,

        COALESCE(p10.production_10j_kwh, 0) AS production_10j_kwh,
        COALESCE(p10.target_10j_kwh, 0) AS target_10j_kwh,
        COALESCE(p10.days_10j_with_kpi, 0) AS days_10j_with_kpi,
        COALESCE(p10.production_days_10j, 0) AS production_days_10j,
        COALESCE(p10.lostcom_days_10j, 0) AS lostcom_days_10j,
        COALESCE(p10.degraded_days_10j, 0) AS degraded_days_10j,

        CASE
            WHEN COALESCE(p10.target_10j_kwh, 0) > 0
            THEN COALESCE(p10.production_10j_kwh, 0) / p10.target_10j_kwh * 100
            ELSE NULL
        END AS performance_10j_pct,

        la.alert_date AS latest_alert_date,
        COALESCE(la.alert_type, '-') AS latest_alert_type,
        COALESCE(la.severity, '-') AS latest_alert_severity,
        COALESCE(la.latest_alert_value, 0) AS latest_alert_value,
        COALESCE(la.latest_alert_status, '-') AS latest_alert_status,
        COALESCE(la.latest_alert_description, '-') AS latest_alert_description,
        la.latest_alert_created_at,

        CASE
            WHEN COALESCE(pa.production_total_kwh, 0) <= 0
            THEN 'PRODUCTION_NULLE'

            WHEN COALESCE(p10.lostcom_days_10j, 0) > 5
            THEN 'LOSTCOM'

            WHEN COALESCE(p10.target_10j_kwh, 0) > 0
             AND COALESCE(p10.production_10j_kwh, 0) < COALESCE(p10.target_10j_kwh, 0) * 0.70
            THEN 'DEGRADE'

            ELSE 'OK'
        END AS statut_10j

    FROM sites s

    LEFT JOIN teams t
    ON t.team_id = s.team_id

    INNER JOIN solar_installation_clean si
        ON si.site_id = s.site_id

    LEFT JOIN production_all pa
        ON pa.site_id = s.site_id

    LEFT JOIN production_10d p10
        ON p10.site_id = s.site_id

    LEFT JOIN latest_alert la
        ON la.site_id = s.site_id
    WHERE
        (
            :selected_batch IS NULL
            OR COALESCE(si.batch, 'Non défini') = :selected_batch
        )

    ORDER BY
        si.batch,
        s.code_site
    """

    df = read_sql(
        query,
        params={
            "selected_batch": selected_batch
        }
    )

    if df.empty:
        return df

    numeric_cols = [
        "panel_quantity",
        "installed_kwc",
        "production_total_kwh",
        "target_total_kwh",
        "total_days_with_kpi",
        "production_days_total",
        "lostcom_days_total",
        "degraded_days_total",
        "production_10j_kwh",
        "target_10j_kwh",
        "days_10j_with_kpi",
        "production_days_10j",
        "lostcom_days_10j",
        "degraded_days_10j",
        "performance_10j_pct",
        "latest_alert_value",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)

    if "installation_date" in df.columns:
        df["installation_date"] = pd.to_datetime(
            df["installation_date"],
            errors="coerce"
        ).dt.date

    return df


def insert_solar_alert(
    site_id,
    alert_date,
    alert_type,
    severity,
    value,
    description,
    status
):
    query = text("""
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
        :alert_date,
        :alert_type,
        :severity,
        :value,
        :description,
        :status,
        NOW()
    );
    """)

    with engine.begin() as conn:
        conn.execute(
            query,
            {
                "site_id": int(site_id),
                "alert_date": alert_date,
                "alert_type": alert_type,
                "severity": severity,
                "value": value,
                "description": description,
                "status": status,
            }
        )

# ==================================================
# PAGE STREAMLIT
# ==================================================

def show_solar_sites_summary():

    st.title("☀️ Synthèse des sites solaires")

    if st.button("🔄 Actualiser", key="refresh_solar_sites_summary"):
        st.cache_data.clear()
        st.rerun()

    st.caption(
        "Analyse par site avec production totale, production des 10 derniers jours, target, panneaux, LOSTCOM et production dégradée < 70%."
    )

    st.divider()

    # ==================================================
    # FILTRE BATCH
    # ==================================================

    df_batches = load_batches()

    if df_batches.empty:
        batch_options = ["TOUS"]
    else:
        batch_options = ["TOUS"] + df_batches["batch"].dropna().tolist()

    selected_batch = st.sidebar.selectbox(
        "Filtre Batch solaire",
        batch_options,
        index=0,
        key="solar_sites_summary_batch_filter"
    )

    selected_batch_param = None

    if selected_batch != "TOUS":
        selected_batch_param = selected_batch

    df = load_solar_sites_summary(selected_batch_param)

    if df.empty:
        st.warning("Aucune donnée disponible pour ce batch.")
        return

    # ==================================================
    # KPI
    # ==================================================

    total_sites = df["site_id"].nunique()
    total_installed_kwc = df["installed_kwc"].sum()
    total_prod_10j = df["production_10j_kwh"].sum()
    total_target_10j = df["target_10j_kwh"].sum()

    performance_10j = 0

    if total_target_10j > 0:
        performance_10j = total_prod_10j / total_target_10j * 100

    total_lostcom_10j = df["lostcom_days_10j"].sum()
    total_degraded_10j = df["degraded_days_10j"].sum()

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric("Sites solaires", f"{total_sites:,.0f}")

    with c2:
        st.metric("Puissance installée", f"{total_installed_kwc:,.1f} kWc")

    with c3:
        st.metric("Production 10 jours", f"{total_prod_10j:,.1f} kWh")

    with c4:
        st.metric("Target 10 jours", f"{total_target_10j:,.1f} kWh")

    with c5:
        st.metric("Performance 10 jours", f"{performance_10j:.1f} %")

    with c6:
        st.metric("Jours dégradés <60%", f"{total_degraded_10j:,.0f}")

    st.divider()

    # ==================================================
    # FILTRES COMPLEMENTAIRES
    # ==================================================

    col1, col2, col3 = st.columns(3)

    with col1:
        status_options = ["TOUS"] + sorted(
            df["statut_10j"]
            .fillna("Non défini")
            .astype(str)
            .unique()
            .tolist()
        )

        selected_status = st.selectbox(
            "Filtre statut 10 jours",
            status_options,
            index=0,
            key="solar_sites_summary_status_filter"
        )

    with col2:
        typologie_options = ["TOUS"] + sorted(
            df["typologie_fms"]
            .fillna("Non défini")
            .astype(str)
            .unique()
            .tolist()
        )

        selected_typologie = st.selectbox(
            "Filtre Typologie FMS",
            typologie_options,
            index=0,
            key="solar_sites_summary_typologie_filter"
        )

    with col3:
        if "latest_alert_type" in df.columns:
            df["latest_alert_type"] = (
                df["latest_alert_type"]
                .fillna("Sans alerte")
                .astype(str)
                .str.strip()
            )

            df.loc[
                df["latest_alert_type"].isin(["", "-", "None", "nan"]),
                "latest_alert_type"
            ] = "Sans alerte"

            alert_type_options = ["TOUS"] + sorted(
                df["latest_alert_type"].unique().tolist()
            )
        else:
            alert_type_options = ["TOUS"]

        selected_alert_type = st.selectbox(
            "Filtre type d'alerte",
            alert_type_options,
            index=0,
            key="solar_sites_summary_alert_type_filter"
        )


    df_filtered = df.copy()

    if selected_status != "TOUS":
        df_filtered = df_filtered[
            df_filtered["statut_10j"] == selected_status
        ].copy()

    if selected_typologie != "TOUS":
        df_filtered = df_filtered[
            df_filtered["typologie_fms"] == selected_typologie
        ].copy()

    if selected_alert_type != "TOUS" and "latest_alert_type" in df_filtered.columns:
        df_filtered = df_filtered[
            df_filtered["latest_alert_type"] == selected_alert_type
        ].copy()

    # ==================================================
    # KPI SELON LES FILTRES SELECTIONNES
    # ==================================================

    st.subheader("📌 KPI selon les filtres sélectionnés")

    total_sites_filtered = df_filtered["site_id"].nunique()

    total_installed_kwc_filtered = df_filtered["installed_kwc"].sum()

    production_total_filtered = df_filtered["production_total_kwh"].sum()

    production_10j_filtered = df_filtered["production_10j_kwh"].sum()

    target_10j_filtered = df_filtered["target_10j_kwh"].sum()

    performance_10j_filtered = 0

    if target_10j_filtered > 0:
        performance_10j_filtered = (
            production_10j_filtered / target_10j_filtered * 100
        )

    production_days_10j_filtered = df_filtered["production_days_10j"].sum()

    lostcom_days_10j_filtered = df_filtered["lostcom_days_10j"].sum()

    degraded_days_10j_filtered = df_filtered["degraded_days_10j"].sum()

    sites_lostcom_filtered = len(
        df_filtered[df_filtered["statut_10j"] == "LOSTCOM"]
    )

    sites_degraded_filtered = len(
        df_filtered[df_filtered["statut_10j"] == "DEGRADE"]
    )

    sites_ok_filtered = len(
        df_filtered[df_filtered["statut_10j"] == "OK"]
    )

    sites_zero_filtered = len(
        df_filtered[df_filtered["statut_10j"] == "PRODUCTION_NULLE"]
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Sites filtrés",
            f"{total_sites_filtered:,.0f}"
        )

    with c2:
        st.metric(
            "Puissance installée",
            f"{total_installed_kwc_filtered:,.1f} kWc"
        )

    with c3:
        st.metric(
            "Production totale",
            f"{production_total_filtered:,.1f} kWh"
        )

    with c4:
        st.metric(
            "Production 10 jours",
            f"{production_10j_filtered:,.1f} kWh"
        )

    c5, c6, c7, c8 = st.columns(4)

    with c5:
        st.metric(
            "Target 10 jours",
            f"{target_10j_filtered:,.1f} kWh"
        )

    with c6:
        st.metric(
            "Performance 10 jours",
            f"{performance_10j_filtered:.1f} %"
        )

    with c7:
        st.metric(
            "Jours LOSTCOM",
            f"{lostcom_days_10j_filtered:,.0f}"
        )

    with c8:
        st.metric(
            "Jours dégradés < 70%",
            f"{degraded_days_10j_filtered:,.0f}"
        )

    c9, c10, c11, c12 = st.columns(4)

    with c9:
        st.metric(
            "Sites OK",
            f"{sites_ok_filtered:,.0f}"
        )

    with c10:
        st.metric(
            "Sites dégradés",
            f"{sites_degraded_filtered:,.0f}"
        )

    with c11:
        st.metric(
            "Sites LOSTCOM",
            f"{sites_lostcom_filtered:,.0f}"
        )

    with c12:
        st.metric(
            "Production nulle",
            f"{sites_zero_filtered:,.0f}"
        )

    st.divider()
# ==================================================
# GRAPH STATUT + CAMEMBERT ALERT TYPE
# ==================================================

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:

        df_status = (
            df_filtered
            .groupby("statut_10j", as_index=False)
            .agg(nombre_sites=("site_id", "nunique"))
            .sort_values("nombre_sites", ascending=False)
        )

        fig_status = px.bar(
            df_status,
            x="statut_10j",
            y="nombre_sites",
            text="nombre_sites",
            title="Répartition des sites selon le statut 10 jours"
        )

        fig_status.update_layout(
            height=450,
            xaxis_title="Statut",
            yaxis_title="Nombre de sites"
        )

        st.plotly_chart(
            fig_status,
            use_container_width=True,
            key="solar_sites_summary_status_chart"
        )


    with chart_col2:

        if "latest_alert_type" not in df_filtered.columns:

            st.info("Aucune colonne latest_alert_type disponible.")

        else:

            df_alert_type = df_filtered.copy()

            df_alert_type["latest_alert_type"] = (
                df_alert_type["latest_alert_type"]
                .fillna("Sans alerte")
                .astype(str)
                .str.strip()
            )

            df_alert_type.loc[
                df_alert_type["latest_alert_type"].isin(["", "-", "None", "nan"]),
                "latest_alert_type"
            ] = "Sans alerte"

            df_alert_type_summary = (
                df_alert_type
                .groupby("latest_alert_type", as_index=False)
                .agg(nombre_sites=("site_id", "nunique"))
                .sort_values("nombre_sites", ascending=False)
            )

            if df_alert_type_summary.empty:

                st.info("Aucune alerte disponible pour le filtre sélectionné.")

            else:

                fig_alert_type = px.pie(
                    df_alert_type_summary,
                    names="latest_alert_type",
                    values="nombre_sites",
                    title="Répartition par type de dernière alerte",
                    hole=0.35
                )

                fig_alert_type.update_layout(
                    height=450
                )

                st.plotly_chart(
                    fig_alert_type,
                    use_container_width=True,
                    key="solar_sites_summary_latest_alert_type_pie"
                )

    # ==================================================
    # TABLEAU DETAIL
    # ==================================================

    st.subheader("📋 Liste complète des sites solaires")

    display_cols = [
        "batch",
        "code_site",
        "site_name",
        "team_name",
        "installation_date",
        "latest_alert_status",
        "latest_alert_type",
        "production_total_kwh",
        "target_total_kwh",
        "production_10j_kwh",
        "target_10j_kwh",
        "performance_10j_pct",
        "production_days_10j",
        "lostcom_days_10j",
        "degraded_days_10j",
        "production_days_total",
        "lostcom_days_total",
        "degraded_days_total",
        "statut_10j",
        "latest_alert_date",
        "latest_alert_severity",
        "latest_alert_description",
         "typologie_fms",
        "panel_type",
        "panel_quantity",
        "installed_kwc",
    ]

    display_cols = [
        col for col in display_cols
        if col in df_filtered.columns
    ]


    def highlight_open_alert(row):
        alert_status = str(row.get("latest_alert_status", "")).strip().upper()

        if alert_status == "OPEN":
            return [
                "background-color: #fecaca; color: #7f1d1d; font-weight: bold"
                for _ in row
            ]

        return ["" for _ in row]



    df_table = df_filtered[display_cols].copy()

    styled_table = df_table.style.apply(
        highlight_open_alert,
        axis=1
    )
    st.dataframe(
        styled_table,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "code_site": st.column_config.Column(
                "Code site",
                pinned=True,
                width="small"
            ),
            "site_name": st.column_config.Column(
                "Nom site",
                pinned=True,
                width="medium"
            ),
            "latest_alert_status": st.column_config.Column(
                "Statut alerte",
                width="small"
            ),
            "latest_alert_description": st.column_config.Column(
                "Description alerte",
                width="large"
            ),
        }
    )

    st.divider()
    st.subheader("➕ Ajouter une alerte par site")

    if "selected_alert_site_id" not in st.session_state:
        st.session_state["selected_alert_site_id"] = None

    if "selected_alert_code_site" not in st.session_state:
        st.session_state["selected_alert_code_site"] = None

    if "selected_alert_site_name" not in st.session_state:
        st.session_state["selected_alert_site_name"] = None


    search_site = st.text_input(
        "Rechercher un site",
        placeholder="Exemple : ABG002",
        key="search_site_for_alert"
    )

    df_alert_buttons = df_filtered.copy()

    if search_site.strip() != "":
        search_value = search_site.strip().upper()

        df_alert_buttons = df_alert_buttons[
            df_alert_buttons["code_site"]
            .astype(str)
            .str.upper()
            .str.contains(search_value, na=False)
        ].copy()

    df_alert_buttons = df_alert_buttons.head(50)

    st.caption(
        "Affichage limité aux 50 premiers sites. Utilisez la recherche pour trouver un site précis."
    )

    for _, row in df_alert_buttons.iterrows():

        col1, col2, col3, col4, col5 = st.columns([1.2, 2.5, 1.5, 1.5, 1])

        with col1:
            st.write(row["code_site"])

        with col2:
            st.write(row["site_name"])

        with col3:
            st.write(row["statut_10j"])

        with col4:
            st.write(f"{row['production_10j_kwh']:.1f} kWh")

        with col5:
            if st.button(
                "➕ Alerte",
                key=f"btn_add_alert_{int(row['site_id'])}"
            ):
                st.session_state["selected_alert_site_id"] = int(row["site_id"])
                st.session_state["selected_alert_code_site"] = row["code_site"]
                st.session_state["selected_alert_site_name"] = row["site_name"]
                st.rerun()

    if st.session_state["selected_alert_site_id"] is not None:

        st.divider()

        st.subheader(
            f"📝 Nouvelle alerte - {st.session_state['selected_alert_code_site']}"
        )

        st.caption(
            st.session_state["selected_alert_site_name"]
        )

        with st.form("form_add_solar_alert"):

            alert_date = st.date_input(
                "Date de l'alerte",
                value=date.today(),
                key="new_alert_date"
            )

            alert_type = st.selectbox(
                "Type d'alerte",
                [
                    "LOW_PRODUCTION",
                    "ZERO_PRODUCTION",
                    "LOSTCOM",
                    "PANEL_ISSUE",
                    "CHARGER_ISSUE",
                    "CABLE_ISSUE",
                    "CLEANING_REQUIRED",
                    "OTHER",
                ],
                key="new_alert_type"
            )

            severity = st.selectbox(
                "Sévérité",
                [
                    "LOW",
                    "MEDIUM",
                    "HIGH",
                    "CRITICAL",
                ],
                key="new_alert_severity"
            )

            value = st.number_input(
                "Valeur liée à l'alerte",
                value=0.0,
                step=0.1,
                key="new_alert_value"
            )

            description = st.text_area(
                "Description",
                placeholder="Exemple : Production inférieure à 70% du target sur les 10 derniers jours.",
                key="new_alert_description"
            )

            status = st.selectbox(
                "Statut",
                [
                    "OPEN",
                    "IN_PROGRESS",
                    "CLOSED",
                ],
                key="new_alert_status"
            )

            col_submit, col_cancel = st.columns(2)

            with col_submit:
                submit_alert = st.form_submit_button("✅ Enregistrer l'alerte")

            with col_cancel:
                cancel_alert = st.form_submit_button("❌ Annuler")

            if submit_alert:

                if description.strip() == "":
                    st.error("La description est obligatoire.")

                else:
                    insert_solar_alert(
                        site_id=st.session_state["selected_alert_site_id"],
                        alert_date=alert_date,
                        alert_type=alert_type,
                        severity=severity,
                        value=value,
                        description=description.strip(),
                        status=status
                    )

                    st.success("Alerte ajoutée avec succès.")

                    st.session_state["selected_alert_site_id"] = None
                    st.session_state["selected_alert_code_site"] = None
                    st.session_state["selected_alert_site_name"] = None

                    st.cache_data.clear()
                    st.rerun()

            if cancel_alert:

                st.session_state["selected_alert_site_id"] = None
                st.session_state["selected_alert_code_site"] = None
                st.session_state["selected_alert_site_name"] = None

                st.rerun()

    csv = df_filtered[display_cols].to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        label="⬇️ Exporter la synthèse solaire CSV",
        data=csv,
        file_name="synthese_sites_solaires.csv",
        mime="text/csv",
        key="download_solar_sites_summary"
    )
