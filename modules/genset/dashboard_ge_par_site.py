import io
from datetime import timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text

from config.database import engine


# =====================================================
# KPI CARD
# =====================================================

def kpi_card(title, value, unit="", color="#111827"):
    st.markdown(
        f"""
        <div style="
            background-color:white;
            border-radius:18px;
            padding:18px;
            box-shadow:0 4px 12px rgba(0,0,0,.12);
            border-top:6px solid {color};
            min-height:115px;
        ">
            <div style="font-size:14px;color:#6b7280;font-weight:600;">
                {title}
            </div>
            <div style="font-size:27px;font-weight:800;color:#111827;margin-top:8px;">
                {value}
            </div>
            <div style="font-size:13px;color:#6b7280;">
                {unit}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =====================================================
# DATA
# =====================================================

@st.cache_data(ttl=300)
def load_sites_with_energy_kpi():
    query = text("""
    SELECT DISTINCT
        s.site_id,
        s.code_site,
        COALESCE(s.site_name, '') AS site_name
    FROM energy_kpi_daily e
    INNER JOIN sites s
        ON s.site_id = e.site_id
    ORDER BY
        s.code_site
    """)

    return pd.read_sql(query, engine)


@st.cache_data(ttl=300)
def get_site_date_range(site_id):
    query = text("""
    SELECT
        MIN(kpi_date) AS min_date,
        MAX(kpi_date) AS max_date
    FROM energy_kpi_daily
    WHERE site_id = :site_id
    """)

    return pd.read_sql(
        query,
        engine,
        params={
            "site_id": site_id
        }
    )


def load_site_energy_kpi(site_id, date_debut, date_fin):
    query = text("""
    SELECT
        e.energy_kpi_id,
        e.site_id,
        s.code_site,
        COALESCE(s.site_name, '') AS site_name,

        e.kpi_date,

        COALESCE(e.load_energy_kwh, 0) AS load_energy_kwh,
        COALESCE(e.solar_energy_kwh, 0) AS solar_energy_kwh,
        COALESCE(e.grid_energy_kwh, 0) AS grid_energy_kwh,
        COALESCE(e.battery_discharge_kwh, 0) AS battery_discharge_kwh,
        COALESCE(e.generator_energy_kwh, 0) AS generator_energy_kwh,

        COALESCE(e.fuel_consumption_l, 0) AS fuel_consumption_l,
        COALESCE(e.generator_runtime_h, 0) AS generator_runtime_h,
        COALESCE(e.generator_starts, 0) AS generator_starts,

        COALESCE(e.soc_min_pct, 0) AS soc_min_pct,
        COALESCE(e.soc_final_pct, 0) AS soc_final_pct,

        COALESCE(e.unserved_load_kwh, 0) AS unserved_load_kwh,

        e.load_source,
        e.solar_source,
        e.grid_source,

        COALESCE(g.rated_power_kva, 0) AS generator_power_kva,
        COALESCE(g.rated_power_kw, 0) AS generator_power_kw,

        sg.grid_date,
        sg.grid_mode,
        sg.grid_availability_pct,
        sg.grid_outages_per_day

    FROM energy_kpi_daily e

    INNER JOIN sites s
        ON s.site_id = e.site_id

    LEFT JOIN genset_installations g
        ON g.site_id = e.site_id
        AND COALESCE(UPPER(TRIM(g.status)), '') = 'ACTIVE'

    LEFT JOIN site_grid sg
        ON sg.site_id = e.site_id
        AND sg.grid_date = e.kpi_date

    WHERE e.site_id = :site_id
      AND e.kpi_date BETWEEN :date_debut AND :date_fin

    ORDER BY
        e.kpi_date
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "site_id": site_id,
            "date_debut": date_debut,
            "date_fin": date_fin,
        }
    )

    if df.empty:
        return df

    df["kpi_date"] = pd.to_datetime(df["kpi_date"])

    numeric_cols = [
        "load_energy_kwh",
        "solar_energy_kwh",
        "grid_energy_kwh",
        "battery_discharge_kwh",
        "generator_energy_kwh",
        "fuel_consumption_l",
        "generator_runtime_h",
        "generator_starts",
        "soc_min_pct",
        "soc_final_pct",
        "unserved_load_kwh",
        "generator_power_kva",
        "generator_power_kw",
        "grid_availability_pct",
        "grid_outages_per_day",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)

    df["fuel_l_per_h"] = 0.0
    df.loc[
        df["generator_runtime_h"] > 0,
        "fuel_l_per_h"
    ] = (
        df["fuel_consumption_l"]
        /
        df["generator_runtime_h"]
    )

    df["fuel_l_per_kwh"] = 0.0
    df.loc[
        df["generator_energy_kwh"] > 0,
        "fuel_l_per_kwh"
    ] = (
        df["fuel_consumption_l"]
        /
        df["generator_energy_kwh"]
    )

    df["ge_dependency_pct"] = 0.0
    df.loc[
        df["load_energy_kwh"] > 0,
        "ge_dependency_pct"
    ] = (
        df["generator_energy_kwh"]
        /
        df["load_energy_kwh"]
        *
        100
    )

    return df


# =====================================================
# PAGE ANALYSE GE PAR SITE
# =====================================================

def show_ge_site_analysis():

    st.title("🔎 Analyse GE par site")

    col_refresh, col_info = st.columns([1, 4])

    with col_refresh:
        if st.button(
            "🔄 Actualiser",
            key="refresh_ge_site_analysis"
        ):
            st.cache_data.clear()
            st.rerun()

    with col_info:
        st.caption(
            "Actualise les données lues depuis energy_kpi_daily."
        )

        df_sites = load_sites_with_energy_kpi()

        if df_sites.empty:
            st.warning("Aucun résultat trouvé dans energy_kpi_daily.")
            return

    df_sites["label"] = (
        df_sites["code_site"].astype(str)
        + " - "
        + df_sites["site_name"].astype(str)
    )

    selected_label = st.sidebar.selectbox(
        "Choisir un site",
        df_sites["label"].tolist()
    )

    site_id = int(
        df_sites.loc[
            df_sites["label"] == selected_label,
            "site_id"
        ].iloc[0]
    )

    site_code = df_sites.loc[
        df_sites["site_id"] == site_id,
        "code_site"
    ].iloc[0]

    df_range = get_site_date_range(site_id)

    if df_range.empty or pd.isna(df_range.iloc[0]["max_date"]):
        st.warning("Aucune date disponible pour ce site.")
        return

    min_date = pd.to_datetime(
        df_range.iloc[0]["min_date"]
    ).date()

    max_date = pd.to_datetime(
        df_range.iloc[0]["max_date"]
    ).date()

    default_start = max(
        min_date,
        max_date - timedelta(days=29)
    )

    st.sidebar.markdown("---")

    date_debut = st.sidebar.date_input(
        "Date début",
        value=default_start,
        min_value=min_date,
        max_value=max_date,
        key="ge_site_date_debut"
    )

    date_fin = st.sidebar.date_input(
        "Date fin",
        value=max_date,
        min_value=min_date,
        max_value=max_date,
        key="ge_site_date_fin"
    )

    if date_debut > date_fin:
        st.error("La date début doit être inférieure ou égale à la date fin.")
        return

    df = load_site_energy_kpi(
        site_id=site_id,
        date_debut=date_debut,
        date_fin=date_fin
    )

    if df.empty:
        st.warning("Aucune donnée trouvée pour ce site et cette période.")
        return

    st.caption(
        f"Site analysé : **{selected_label}** | "
        f"Période : **{date_debut} → {date_fin}**"
    )

    # =====================================================
    # KPI
    # =====================================================

    nb_days = len(df)
    nb_days_ge = int((df["generator_runtime_h"] > 0).sum())
    nb_days_ge_h24 = int((df["generator_runtime_h"] >= 23).sum())

    total_load = df["load_energy_kwh"].sum()
    total_solar = df["solar_energy_kwh"].sum()
    total_grid = df["grid_energy_kwh"].sum()
    total_ge_energy = df["generator_energy_kwh"].sum()
    total_battery = df["battery_discharge_kwh"].sum()

    total_fuel = df["fuel_consumption_l"].sum()
    total_ge_hours = df["generator_runtime_h"].sum()
    total_starts = df["generator_starts"].sum()
    total_unserved = df["unserved_load_kwh"].sum()

    avg_lph = 0
    if total_ge_hours > 0:
        avg_lph = total_fuel / total_ge_hours

    avg_lpkwh = 0
    if total_ge_energy > 0:
        avg_lpkwh = total_fuel / total_ge_energy

    ge_dependency = 0
    if total_load > 0:
        ge_dependency = total_ge_energy / total_load * 100

    soc_min = df["soc_min_pct"].min()
    soc_final = df["soc_final_pct"].iloc[-1]

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        kpi_card(
            "Jours analysés",
            f"{nb_days:,.0f}",
            "",
            "#2563eb"
        )

    with c2:
        kpi_card(
            "Fuel GE",
            f"{total_fuel:,.1f}",
            "L",
            "#dc2626"
        )

    with c3:
        kpi_card(
            "Heures GE",
            f"{total_ge_hours:,.1f}",
            "h",
            "#f97316"
        )

    with c4:
        kpi_card(
            "Énergie GE",
            f"{total_ge_energy:,.1f}",
            "kWh",
            "#111827"
        )

    st.write("")

    c5, c6, c7, c8 = st.columns(4)

    with c5:
        kpi_card(
            "Conso moyenne",
            f"{avg_lph:,.2f}",
            "L/h",
            "#7c3aed"
        )

    with c6:
        kpi_card(
            "Fuel spécifique",
            f"{avg_lpkwh:,.3f}",
            "L/kWh GE",
            "#9333ea"
        )

    with c7:
        kpi_card(
            "Dépendance GE",
            f"{ge_dependency:,.1f}",
            "% du load",
            "#b91c1c"
        )

    with c8:
        kpi_card(
            "Jours GE H24",
            f"{nb_days_ge_h24:,.0f}",
            "GE ≥ 23 h/j",
            "#991b1b"
        )

    st.write("")

    c9, c10, c11, c12 = st.columns(4)

    with c9:
        kpi_card(
            "Énergie Grid",
            f"{total_grid:,.1f}",
            "kWh",
            "#16a34a"
        )

    with c10:
        kpi_card(
            "Démarrages GE",
            f"{total_starts:,.0f}",
            "",
            "#0f766e"
        )

    with c11:
        kpi_card(
            "SOC min",
            f"{soc_min:,.1f}",
            "%",
            "#ca8a04"
        )

    with c12:
        kpi_card(
            "Load non servi",
            f"{total_unserved:,.2f}",
            "kWh",
            "#dc2626"
        )

    st.divider()

    # =====================================================
    # GRAPHE 1 : FUEL ET HEURES GE
    # =====================================================

    st.subheader("⛽ Fuel et heures GE par jour")

    fig_runtime_fuel = go.Figure()

    fig_runtime_fuel.add_trace(
        go.Bar(
            x=df["kpi_date"],
            y=df["generator_runtime_h"],
            name="Heures GE",
            text=df["generator_runtime_h"].round(1),
            textposition="outside"
        )
    )

    fig_runtime_fuel.add_trace(
        go.Scatter(
            x=df["kpi_date"],
            y=df["fuel_consumption_l"],
            mode="lines+markers",
            name="Fuel GE (L)",
            yaxis="y2"
        )
    )

    fig_runtime_fuel.update_layout(
        height=500,
        title=f"Fuel et heures GE - {site_code}",
        xaxis_title="Date",
        yaxis=dict(
            title="Heures GE (h)"
        ),
        yaxis2=dict(
            title="Fuel GE (L)",
            overlaying="y",
            side="right"
        ),
        legend=dict(
            orientation="h"
        )
    )

    st.plotly_chart(
        fig_runtime_fuel,
        use_container_width=True,
        key="ge_site_chart_runtime_fuel"
    )

    st.divider()

    # =====================================================
    # GRAPHE 2 : ENERGIE PAR SOURCE
    # =====================================================

    st.subheader("⚡ Énergie journalière par source")

    fig_energy_sources = go.Figure()

    fig_energy_sources.add_trace(
        go.Bar(
            x=df["kpi_date"],
            y=df["load_energy_kwh"],
            name="Load"
        )
    )

    fig_energy_sources.add_trace(
        go.Bar(
            x=df["kpi_date"],
            y=df["solar_energy_kwh"],
            name="Solaire"
        )
    )

    fig_energy_sources.add_trace(
        go.Bar(
            x=df["kpi_date"],
            y=df["grid_energy_kwh"],
            name="Grid"
        )
    )

    fig_energy_sources.add_trace(
        go.Bar(
            x=df["kpi_date"],
            y=df["generator_energy_kwh"],
            name="GE"
        )
    )

    fig_energy_sources.update_layout(
        barmode="group",
        height=520,
        title=f"Énergie par source - {site_code}",
        xaxis_title="Date",
        yaxis_title="Énergie (kWh)",
        legend=dict(
            orientation="h"
        )
    )

    st.plotly_chart(
        fig_energy_sources,
        use_container_width=True,
        key="ge_site_chart_energy_sources"
    )

    st.divider()

    # =====================================================
    # GRAPHE 3 : DISPONIBILITE GRID VS GE
    # =====================================================

    st.subheader("🔌 Disponibilité Grid vs heures GE")

    fig_grid_vs_ge = go.Figure()

    fig_grid_vs_ge.add_trace(
        go.Bar(
            x=df["kpi_date"],
            y=df["generator_runtime_h"],
            name="Heures GE"
        )
    )

    fig_grid_vs_ge.add_trace(
        go.Scatter(
            x=df["kpi_date"],
            y=df["grid_availability_pct"],
            mode="lines+markers",
            name="Disponibilité Grid (%)",
            yaxis="y2"
        )
    )

    fig_grid_vs_ge.update_layout(
        height=500,
        title=f"Impact disponibilité Grid sur GE - {site_code}",
        xaxis_title="Date",
        yaxis=dict(
            title="Heures GE (h)"
        ),
        yaxis2=dict(
            title="Disponibilité Grid (%)",
            overlaying="y",
            side="right",
            range=[0, 100]
        ),
        legend=dict(
            orientation="h"
        )
    )

    st.plotly_chart(
        fig_grid_vs_ge,
        use_container_width=True,
        key="ge_site_chart_grid_vs_ge"
    )

    st.divider()

    # =====================================================
    # GRAPHE 4 : PERFORMANCE GE
    # =====================================================

    st.subheader("📈 Performance GE")

    fig_ge_perf = go.Figure()

    fig_ge_perf.add_trace(
        go.Scatter(
            x=df["kpi_date"],
            y=df["fuel_l_per_h"],
            mode="lines+markers",
            name="L/h"
        )
    )

    fig_ge_perf.add_trace(
        go.Scatter(
            x=df["kpi_date"],
            y=df["fuel_l_per_kwh"],
            mode="lines+markers",
            name="L/kWh GE",
            yaxis="y2"
        )
    )

    fig_ge_perf.update_layout(
        height=500,
        title=f"Consommation spécifique GE - {site_code}",
        xaxis_title="Date",
        yaxis=dict(
            title="L/h"
        ),
        yaxis2=dict(
            title="L/kWh",
            overlaying="y",
            side="right"
        ),
        legend=dict(
            orientation="h"
        )
    )

    st.plotly_chart(
        fig_ge_perf,
        use_container_width=True,
        key="ge_site_chart_performance"
    )

    st.divider()

    # =====================================================
    # GRAPHE 5 : SOC BATTERIE
    # =====================================================

    st.subheader("🔋 SOC batterie")

    fig_soc = go.Figure()

    fig_soc.add_trace(
        go.Scatter(
            x=df["kpi_date"],
            y=df["soc_min_pct"],
            mode="lines+markers",
            name="SOC min"
        )
    )

    fig_soc.add_trace(
        go.Scatter(
            x=df["kpi_date"],
            y=df["soc_final_pct"],
            mode="lines+markers",
            name="SOC final"
        )
    )

    fig_soc.update_layout(
        height=450,
        title=f"SOC batterie - {site_code}",
        xaxis_title="Date",
        yaxis_title="SOC (%)",
        yaxis=dict(
            range=[0, 100]
        ),
        legend=dict(
            orientation="h"
        )
    )

    st.plotly_chart(
        fig_soc,
        use_container_width=True,
        key="ge_site_chart_soc"
    )

    st.divider()

    # =====================================================
    # TABLE DETAILS
    # =====================================================

    st.subheader("📋 Détail KPI GE par jour")

    df_display = df[
        [
            "kpi_date",
            "code_site",
            "site_name",
            "load_energy_kwh",
            "solar_energy_kwh",
            "grid_energy_kwh",
            "generator_energy_kwh",
            "fuel_consumption_l",
            "generator_runtime_h",
            "generator_starts",
            "fuel_l_per_h",
            "fuel_l_per_kwh",
            "ge_dependency_pct",
            "grid_availability_pct",
            "grid_outages_per_day",
            "soc_min_pct",
            "soc_final_pct",
            "unserved_load_kwh",
            "load_source",
            "solar_source",
            "grid_source",
        ]
    ].copy()

    df_display["kpi_date"] = df_display["kpi_date"].dt.date

    st.dataframe(
        df_display,
        use_container_width=True,
        height=500
    )

    # =====================================================
    # EXPORT EXCEL
    # =====================================================

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        df_display.to_excel(
            writer,
            index=False,
            sheet_name="GE par jour"
        )

        summary_df = pd.DataFrame(
            [
                {
                    "site": site_code,
                    "date_debut": date_debut,
                    "date_fin": date_fin,
                    "jours_analyses": nb_days,
                    "jours_ge_on": nb_days_ge,
                    "jours_ge_h24": nb_days_ge_h24,
                    "load_kwh": total_load,
                    "solar_kwh": total_solar,
                    "grid_kwh": total_grid,
                    "ge_energy_kwh": total_ge_energy,
                    "battery_discharge_kwh": total_battery,
                    "fuel_l": total_fuel,
                    "ge_hours": total_ge_hours,
                    "generator_starts": total_starts,
                    "avg_lph": avg_lph,
                    "avg_lpkwh": avg_lpkwh,
                    "ge_dependency_pct": ge_dependency,
                    "soc_min_pct": soc_min,
                    "soc_final_pct": soc_final,
                    "unserved_load_kwh": total_unserved,
                }
            ]
        )

        summary_df.to_excel(
            writer,
            index=False,
            sheet_name="Synthese"
        )

    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger analyse GE du site",
        data=buffer,
        file_name=f"analyse_ge_{site_code}_{date_debut}_{date_fin}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_ge_site_analysis"
    )