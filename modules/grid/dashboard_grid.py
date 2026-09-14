import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text

from config.database import engine


# ==================================================
# OUTILS
# ==================================================

def read_sql(query, params=None):
    """
    Lecture SQL sécurisée avec connexion propre.
    Évite le problème :
    Can't reconnect until invalid transaction is rolled back
    """

    with engine.connect() as conn:
        return pd.read_sql(
            text(query),
            conn,
            params=params or {}
        )


@st.cache_data(ttl=300)
def load_grid_dates():

    query = """
    SELECT DISTINCT
        grid_date
    FROM site_grid
    WHERE grid_date IS NOT NULL
    ORDER BY grid_date DESC
    """

    return read_sql(query)


@st.cache_data(ttl=300)
def load_grid_daily_status(grid_date):

    query = """
    SELECT
        s.site_id,
        s.code_site,
        s.site_name,
        COALESCE(s.typologie_fms, 'Non défini') AS typologie_fms,

        g.grid_date,
        COALESCE(g.grid_mode, 'NO_DATA') AS grid_mode,
        COALESCE(g.status, 'NO_DATA') AS status,
        g.grid_availability_pct,
        g.grid_outages_per_day,
        COALESCE(g.source, '-') AS source

    FROM site_grid g

    JOIN sites s
        ON s.site_id = g.site_id

    WHERE g.grid_date = :grid_date

    ORDER BY
        s.code_site
    """

    df = read_sql(
        query,
        params={
            "grid_date": grid_date
        }
    )

    return df


@st.cache_data(ttl=300)
def load_grid_monthly_comparison():

    query = """
    SELECT
        site_id,
        code_site,
        site_name,
        COALESCE(typologie_fms, 'Non défini') AS typologie_fms,

        grid_month,

        actual_grid_kwh,
        simulated_grid_kwh,
        grid_gap_kwh,
        grid_gap_pct,

        simulated_days,
        simulated_load_kwh,
        simulated_solar_kwh,
        simulated_generator_kwh,

        source,
        comment,
        updated_at

    FROM v_grid_monthly_comparison

    ORDER BY
        grid_month DESC,
        code_site
    """

    return read_sql(query)


# ==================================================
# DASHBOARD GRID
# ==================================================

def show_dashboard_grid():

    st.title("⚡ Dashboard Grid")

    if st.button("🔄 Actualiser", key="refresh_grid_dashboard"):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # ==================================================
    # 1. GRID JOURNALIER
    # ==================================================

    st.subheader("📅 État Grid journalier")

    df_dates = load_grid_dates()

    if df_dates.empty:
        st.warning("Aucune donnée disponible dans la table site_grid.")
        st.stop()

    df_dates["grid_date"] = pd.to_datetime(
        df_dates["grid_date"],
        errors="coerce"
    ).dt.date

    grid_dates = df_dates["grid_date"].dropna().tolist()

    selected_date = st.selectbox(
        "Date Grid",
        grid_dates,
        index=0,
        key="grid_dashboard_date"
    )

    df_grid = load_grid_daily_status(selected_date)

    if df_grid.empty:
        st.warning("Aucune donnée Grid pour cette date.")
        st.stop()

    df_grid["grid_mode_clean"] = (
        df_grid["grid_mode"]
        .fillna("NO_DATA")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df_grid["status_clean"] = (
        df_grid["status"]
        .fillna("NO_DATA")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df_grid["typologie_fms"] = (
        df_grid["typologie_fms"]
        .fillna("Non défini")
        .astype(str)
        .str.strip()
    )

    typologie_options = ["TOUS"] + sorted(
        df_grid["typologie_fms"].unique().tolist()
    )

    selected_typologie = st.selectbox(
        "Filtre Typologie FMS",
        typologie_options,
        index=0,
        key="grid_typologie_filter"
    )

    if selected_typologie != "TOUS":
        df_grid = df_grid[
            df_grid["typologie_fms"] == selected_typologie
        ].copy()

    total_sites = df_grid["site_id"].nunique()

    on_grid_sites = df_grid[
        (df_grid["grid_mode_clean"] == "ON_GRID")
        & (df_grid["status_clean"] != "LOSTCOM")
    ]["site_id"].nunique()

    off_grid_sites = df_grid[
        df_grid["grid_mode_clean"] == "OFF_GRID"
    ]["site_id"].nunique()

    lostcom_sites = df_grid[
        (df_grid["grid_mode_clean"] == "LOSTCOM")
        | (df_grid["status_clean"] == "LOSTCOM")
    ]["site_id"].nunique()

    avg_availability = pd.to_numeric(
        df_grid["grid_availability_pct"],
        errors="coerce"
    ).mean()

    total_outages = pd.to_numeric(
        df_grid["grid_outages_per_day"],
        errors="coerce"
    ).fillna(0).sum()

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric("Sites", f"{total_sites:,.0f}")

    with c2:
        st.metric("ON_GRID", f"{on_grid_sites:,.0f}")

    with c3:
        st.metric("OFF_GRID", f"{off_grid_sites:,.0f}")

    with c4:
        st.metric("LOSTCOM", f"{lostcom_sites:,.0f}")

    with c5:
        st.metric(
            "Disponibilité moyenne",
            f"{avg_availability:.1f} %" if pd.notna(avg_availability) else "-"
        )

    with c6:
        st.metric("Coupures/jour", f"{total_outages:,.0f}")

    st.divider()

    # ==================================================
    # 2. GRAPHIQUE STATUT GRID
    # ==================================================

    df_status = (
        df_grid
        .groupby("grid_mode_clean", as_index=False)
        .agg(nombre_sites=("site_id", "nunique"))
        .sort_values("nombre_sites", ascending=False)
    )

    fig_status = px.bar(
        df_status,
        x="grid_mode_clean",
        y="nombre_sites",
        text="nombre_sites",
        title=f"Répartition Grid - {selected_date}"
    )

    fig_status.update_layout(
        height=450,
        xaxis_title="Mode Grid",
        yaxis_title="Nombre de sites"
    )

    st.plotly_chart(
        fig_status,
        use_container_width=True,
        key="grid_daily_status_chart"
    )

    # ==================================================
    # 3. TABLEAU DETAIL GRID JOURNALIER
    # ==================================================

    st.subheader("📋 Détail Grid par site")

    display_cols = [
        "code_site",
        "site_name",
        "typologie_fms",
        "grid_date",
        "grid_mode",
        "status",
        "grid_availability_pct",
        "grid_outages_per_day",
        "source",
    ]

    st.dataframe(
        df_grid[display_cols],
        use_container_width=True,
        hide_index=True,
        height=450
    )

    st.divider()

    # ==================================================
    # 4. COMPARAISON GRID REEL VS SIMULE
    # ==================================================

    st.subheader("🔌 Comparaison consommation Grid réelle vs simulée")

    try:
        df_compare = load_grid_monthly_comparison()

    except Exception as e:
        st.warning(
            "La vue v_grid_monthly_comparison n'est pas disponible ou contient une erreur."
        )
        st.exception(e)
        return

    if df_compare.empty:
        st.info("Aucune donnée de comparaison Grid réel vs simulé.")
        return

    df_compare["grid_month"] = pd.to_datetime(
        df_compare["grid_month"],
        errors="coerce"
    ).dt.date

    numeric_cols = [
        "actual_grid_kwh",
        "simulated_grid_kwh",
        "grid_gap_kwh",
        "grid_gap_pct",
        "simulated_days",
        "simulated_load_kwh",
        "simulated_solar_kwh",
        "simulated_generator_kwh",
    ]

    for col in numeric_cols:
        df_compare[col] = pd.to_numeric(
            df_compare[col],
            errors="coerce"
        ).fillna(0)

    month_options = ["TOUS"] + sorted(
        df_compare["grid_month"].dropna().unique().tolist(),
        reverse=True
    )

    selected_month = st.selectbox(
        "Mois de comparaison",
        month_options,
        index=0,
        key="grid_monthly_comparison_month"
    )

    typologie_options_compare = ["TOUS"] + sorted(
        df_compare["typologie_fms"]
        .fillna("Non défini")
        .astype(str)
        .unique()
        .tolist()
    )

    selected_typologie_compare = st.selectbox(
        "Typologie FMS - comparaison",
        typologie_options_compare,
        index=0,
        key="grid_monthly_typologie_filter"
    )

    df_compare_filtered = df_compare.copy()

    if selected_month != "TOUS":
        df_compare_filtered = df_compare_filtered[
            df_compare_filtered["grid_month"] == selected_month
        ].copy()

    if selected_typologie_compare != "TOUS":
        df_compare_filtered = df_compare_filtered[
            df_compare_filtered["typologie_fms"] == selected_typologie_compare
        ].copy()

    actual_total = df_compare_filtered["actual_grid_kwh"].sum()
    simulated_total = df_compare_filtered["simulated_grid_kwh"].sum()
    gap_total = actual_total - simulated_total

    if actual_total > 0:
        gap_pct_total = gap_total / actual_total * 100
    else:
        gap_pct_total = 0

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Grid réel",
            f"{actual_total:,.1f} kWh"
        )

    with c2:
        st.metric(
            "Grid simulé",
            f"{simulated_total:,.1f} kWh"
        )

    with c3:
        st.metric(
            "Écart kWh",
            f"{gap_total:,.1f} kWh"
        )

    with c4:
        st.metric(
            "Écart %",
            f"{gap_pct_total:.1f} %"
        )

    # ==================================================
    # 5. EVOLUTION MENSUELLE
    # ==================================================

    df_monthly = (
        df_compare_filtered
        .groupby("grid_month", as_index=False)
        .agg(
            actual_grid_kwh=("actual_grid_kwh", "sum"),
            simulated_grid_kwh=("simulated_grid_kwh", "sum"),
            grid_gap_kwh=("grid_gap_kwh", "sum"),
            sites=("site_id", "nunique")
        )
        .sort_values("grid_month")
    )

    if not df_monthly.empty:

        fig_month = px.line(
            df_monthly,
            x="grid_month",
            y=[
                "actual_grid_kwh",
                "simulated_grid_kwh",
            ],
            markers=True,
            title="Évolution mensuelle Grid réel vs simulé"
        )

        fig_month.update_layout(
            height=450,
            xaxis_title="Mois",
            yaxis_title="Consommation Grid (kWh)",
            legend_title="Indicateur"
        )

        st.plotly_chart(
            fig_month,
            use_container_width=True,
            key="grid_monthly_real_vs_simulated"
        )

        fig_gap = px.bar(
            df_monthly,
            x="grid_month",
            y="grid_gap_kwh",
            text="grid_gap_kwh",
            title="Écart mensuel Grid réel - simulé"
        )

        fig_gap.update_layout(
            height=450,
            xaxis_title="Mois",
            yaxis_title="Écart Grid (kWh)"
        )

        st.plotly_chart(
            fig_gap,
            use_container_width=True,
            key="grid_monthly_gap"
        )

    # ==================================================
    # 6. TOP ECARTS PAR SITE
    # ==================================================

    st.subheader("📉 Top écarts Grid par site")

    df_top_gap = df_compare_filtered.copy()

    df_top_gap["abs_gap"] = df_top_gap["grid_gap_kwh"].abs()

    df_top_gap = df_top_gap.sort_values(
        "abs_gap",
        ascending=False
    ).head(30)

    if not df_top_gap.empty:

        fig_top = px.bar(
            df_top_gap,
            x="grid_gap_kwh",
            y="code_site",
            orientation="h",
            text="grid_gap_kwh",
            title="Top 30 sites avec écart Grid réel - simulé"
        )

        fig_top.update_layout(
            height=max(500, len(df_top_gap) * 22),
            xaxis_title="Écart Grid kWh",
            yaxis_title="Site",
            yaxis=dict(autorange="reversed")
        )

        st.plotly_chart(
            fig_top,
            use_container_width=True,
            key="grid_top_gap_sites"
        )

    # ==================================================
    # 7. TABLE DETAIL COMPARAISON
    # ==================================================

    st.subheader("📋 Détail comparaison Grid réel vs simulé")

    detail_cols = [
        "grid_month",
        "code_site",
        "site_name",
        "typologie_fms",
        "actual_grid_kwh",
        "simulated_grid_kwh",
        "grid_gap_kwh",
        "grid_gap_pct",
        "simulated_days",
        "simulated_load_kwh",
        "simulated_solar_kwh",
        "simulated_generator_kwh",
        "source",
        "comment",
    ]

    detail_cols = [
        col for col in detail_cols
        if col in df_compare_filtered.columns
    ]

    st.dataframe(
        df_compare_filtered[detail_cols],
        use_container_width=True,
        hide_index=True,
        height=500
    )

    csv = df_compare_filtered[detail_cols].to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        label="⬇️ Exporter comparaison Grid CSV",
        data=csv,
        file_name="grid_reel_vs_simule.csv",
        mime="text/csv",
        key="download_grid_comparison_csv"
    )