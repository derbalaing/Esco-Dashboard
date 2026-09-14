import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px




from config.database import engine


# =====================================================
# OUTILS AFFICHAGE
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
            min-height:120px;
        ">
            <div style="font-size:14px;color:#6b7280;font-weight:600;">
                {title}
            </div>
            <div style="font-size:28px;font-weight:800;color:#111827;margin-top:8px;">
                {value}
            </div>
            <div style="font-size:13px;color:#6b7280;">
                {unit}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def get_latest_date():
    query = """
    SELECT MAX(kpi_date) AS latest_date
    FROM energy_kpi_daily
    """

    df = pd.read_sql(query, engine)

    if df.empty or pd.isna(df.iloc[0]["latest_date"]):
        return None

    return pd.to_datetime(df.iloc[0]["latest_date"]).date()


# =====================================================
# DASHBOARD GE
# =====================================================

def show_dashboard():

    st.title("⚡ Dashboard GE & Énergie")

    latest_date = get_latest_date()

    if latest_date is None:
        st.warning("Aucune donnée trouvée dans energy_kpi_daily.")
        return

    # =====================================================
    # FILTRES
    # =====================================================

    st.sidebar.header("Filtres Dashboard GE")

    mode_periode = st.sidebar.selectbox(
        "Période",
        [
            "Dernier jour disponible",
            "7 derniers jours",
            "30 derniers jours",
            "Période personnalisée",
        ]
    )

    if mode_periode == "Dernier jour disponible":

        date_debut = latest_date
        date_fin = latest_date

    elif mode_periode == "7 derniers jours":

        date_fin = latest_date
        date_debut = latest_date - pd.Timedelta(days=6)

    elif mode_periode == "30 derniers jours":

        date_fin = latest_date
        date_debut = latest_date - pd.Timedelta(days=29)

    else:

        c1, c2 = st.sidebar.columns(2)

        with c1:
            date_debut = st.date_input(
                "Date début",
                value=latest_date - pd.Timedelta(days=6)
            )

        with c2:
            date_fin = st.date_input(
                "Date fin",
                value=latest_date
            )

    st.caption(
        f"Période analysée : {date_debut} → {date_fin}"
    )

    # =====================================================
    # CHARGEMENT DONNEES
    # =====================================================

    query = """
    SELECT
        e.energy_kpi_id,
        e.site_id,
        s.code_site,
        s.site_name,

        e.kpi_date,

        e.load_energy_kwh,
        e.solar_energy_kwh,
        e.grid_energy_kwh,
        e.battery_discharge_kwh,
        e.generator_energy_kwh,

        e.fuel_consumption_l,
        e.generator_runtime_h,
        e.generator_starts,

        e.soc_min_pct,
        e.soc_final_pct,

        e.unserved_load_kwh,

        e.load_source,
        e.solar_source,
        e.grid_source,

        e.simulation_hours,
        e.dt_min

    FROM energy_kpi_daily e

    INNER JOIN sites s
        ON s.site_id = e.site_id

    WHERE e.kpi_date BETWEEN %(date_debut)s AND %(date_fin)s

    ORDER BY
        e.kpi_date,
        s.code_site
    """

    df = pd.read_sql(
        query,
        engine,
        params={
            "date_debut": date_debut,
            "date_fin": date_fin,
        }
    )

    if df.empty:
        st.warning("Aucune donnée trouvée pour cette période.")
        return

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
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)

    # =====================================================
    # KPI PRINCIPAUX
    # =====================================================

    sites_simules = df["site_id"].nunique()

    total_load = df["load_energy_kwh"].sum()
    total_solar = df["solar_energy_kwh"].sum()
    total_grid = df["grid_energy_kwh"].sum()
    total_ge_energy = df["generator_energy_kwh"].sum()

    total_fuel = df["fuel_consumption_l"].sum()
    total_ge_hours = df["generator_runtime_h"].sum()
    total_starts = df["generator_starts"].sum()

    total_unserved = df["unserved_load_kwh"].sum()

    sites_ge_h24 = df[
        df["generator_runtime_h"] >= 23
    ]["site_id"].nunique()

    sites_unserved = df[
        df["unserved_load_kwh"] > 0
    ]["site_id"].nunique()

    avg_fuel_per_hour = 0

    if total_ge_hours > 0:
        avg_fuel_per_hour = total_fuel / total_ge_hours

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        kpi_card(
            "Sites simulés",
            f"{sites_simules:,.0f}",
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
            "Consommation moyenne GE",
            f"{avg_fuel_per_hour:,.2f}",
            "L/h",
            "#7c3aed"
        )

    st.write("")

    c5, c6, c7, c8 = st.columns(4)

    with c5:
        kpi_card(
            "Énergie Grid",
            f"{total_grid:,.1f}",
            "kWh",
            "#16a34a"
        )

    with c6:
        kpi_card(
            "Énergie GE",
            f"{total_ge_energy:,.1f}",
            "kWh",
            "#111827"
        )

    with c7:
        kpi_card(
            "Sites GE H24",
            f"{sites_ge_h24:,.0f}",
            "GE ≥ 23 h/j",
            "#b91c1c"
        )

    with c8:
        kpi_card(
            "Load non servi",
            f"{total_unserved:,.2f}",
            f"kWh | {sites_unserved} sites",
            "#9333ea"
        )

    st.divider()

    # =====================================================
    # COURBES JOURNALIERES
    # =====================================================

    df_daily = (
        df.groupby("kpi_date")
        .agg(
            load_energy_kwh=("load_energy_kwh", "sum"),
            solar_energy_kwh=("solar_energy_kwh", "sum"),
            grid_energy_kwh=("grid_energy_kwh", "sum"),
            generator_energy_kwh=("generator_energy_kwh", "sum"),
            fuel_consumption_l=("fuel_consumption_l", "sum"),
            generator_runtime_h=("generator_runtime_h", "sum"),
            unserved_load_kwh=("unserved_load_kwh", "sum"),
            sites=("site_id", "nunique"),
        )
        .reset_index()
    )

    st.subheader("📈 Évolution journalière")

    fig_daily = go.Figure()

    fig_daily.add_trace(
        go.Scatter(
            x=df_daily["kpi_date"],
            y=df_daily["fuel_consumption_l"],
            mode="lines+markers",
            name="Fuel GE (L)"
        )
    )

    fig_daily.add_trace(
        go.Scatter(
            x=df_daily["kpi_date"],
            y=df_daily["generator_runtime_h"],
            mode="lines+markers",
            name="Heures GE (h)",
            yaxis="y2"
        )
    )

    fig_daily.update_layout(
        height=500,
        title="Fuel GE et heures GE",
        yaxis=dict(
            title="Fuel GE (L)"
        ),
        yaxis2=dict(
            title="Heures GE (h)",
            overlaying="y",
            side="right"
        ),
        legend=dict(
            orientation="h"
        )
    )

    st.plotly_chart(
        fig_daily,
        use_container_width=True
    )

    st.divider()

    # =====================================================
    # ENERGIE PAR SOURCE
    # =====================================================

    st.subheader("⚡ Énergie par source")

    energy_values = {
        "Load": total_load,
        "Solaire": total_solar,
        "Grid": total_grid,
        "GE": total_ge_energy,
        "Batterie": df["battery_discharge_kwh"].sum(),
    }

    df_energy = pd.DataFrame(
        {
            "Source": list(energy_values.keys()),
            "Énergie kWh": list(energy_values.values()),
        }
    )

    fig_energy = px.bar(
        df_energy,
        x="Source",
        y="Énergie kWh",
        text="Énergie kWh",
        title="Répartition énergie sur la période"
    )

    fig_energy.update_traces(
        texttemplate="%{text:.1f}",
        textposition="outside"
    )

    fig_energy.update_layout(
        height=450
    )

    st.plotly_chart(
        fig_energy,
        use_container_width=True
    )

    st.divider()

    # =====================================================
    # TOP SITES FUEL
    # =====================================================

    st.subheader("⛽ Top sites consommation fuel")

    df_site = (
        df.groupby(
            [
                "site_id",
                "code_site",
                "site_name",
            ]
        )
        .agg(
            fuel_consumption_l=("fuel_consumption_l", "sum"),
            generator_runtime_h=("generator_runtime_h", "sum"),
            generator_energy_kwh=("generator_energy_kwh", "sum"),
            grid_energy_kwh=("grid_energy_kwh", "sum"),
            load_energy_kwh=("load_energy_kwh", "sum"),
            unserved_load_kwh=("unserved_load_kwh", "sum"),
            soc_min_pct=("soc_min_pct", "min"),
            soc_final_pct=("soc_final_pct", "last"),
        )
        .reset_index()
    )

    df_top_fuel = df_site.sort_values(
        "fuel_consumption_l",
        ascending=False
    ).head(20)

    fig_top_fuel = px.bar(
        df_top_fuel,
        x="fuel_consumption_l",
        y="code_site",
        orientation="h",
        text="fuel_consumption_l",
        hover_data=[
            "site_name",
            "generator_runtime_h",
            "generator_energy_kwh",
            "grid_energy_kwh",
            "load_energy_kwh",
        ],
        title="Top 20 sites par fuel GE"
    )

    fig_top_fuel.update_traces(
        texttemplate="%{text:.1f}",
        textposition="outside"
    )

    fig_top_fuel.update_layout(
        height=650,
        yaxis=dict(
            autorange="reversed"
        )
    )

    st.plotly_chart(
        fig_top_fuel,
        use_container_width=True
    )

    st.divider()

    # =====================================================
    # TOP SITES HEURES GE
    # =====================================================

    st.subheader("⏱️ Top sites heures GE")

    df_top_hours = df_site.sort_values(
        "generator_runtime_h",
        ascending=False
    ).head(20)

    fig_top_hours = px.bar(
        df_top_hours,
        x="generator_runtime_h",
        y="code_site",
        orientation="h",
        text="generator_runtime_h",
        hover_data=[
            "site_name",
            "fuel_consumption_l",
            "generator_energy_kwh",
            "grid_energy_kwh",
        ],
        title="Top 20 sites par heures GE"
    )

    fig_top_hours.update_traces(
        texttemplate="%{text:.1f}",
        textposition="outside"
    )

    fig_top_hours.update_layout(
        height=650,
        yaxis=dict(
            autorange="reversed"
        )
    )

    st.plotly_chart(
        fig_top_hours,
        use_container_width=True
    )

    st.divider()

    # =====================================================
    # SITES AVEC LOAD NON SERVI
    # =====================================================

    st.subheader("🚨 Sites avec load non servi")

    df_unserved = df_site[
        df_site["unserved_load_kwh"] > 0
    ].sort_values(
        "unserved_load_kwh",
        ascending=False
    )

    if df_unserved.empty:
        st.success("Aucun load non servi sur la période.")
    else:
        st.dataframe(
            df_unserved[
                [
                    "code_site",
                    "site_name",
                    "unserved_load_kwh",
                    "fuel_consumption_l",
                    "generator_runtime_h",
                    "soc_min_pct",
                    "soc_final_pct",
                ]
            ],
            use_container_width=True
        )

    st.divider()

    # =====================================================
    # TABLEAU DETAILLE
    # =====================================================

    st.subheader("📋 Détail simulation par site")

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
            "soc_min_pct",
            "soc_final_pct",
            "unserved_load_kwh",
            "load_source",
            "solar_source",
            "grid_source",
        ]
    ].sort_values(
        [
            "kpi_date",
            "code_site",
        ],
        ascending=[
            False,
            True,
        ]
    )

    st.dataframe(
        df_display,
        use_container_width=True,
        height=600
    )

    # =====================================================
    # EXPORT EXCEL
    # =====================================================

    import io

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:
        df_display.to_excel(
            writer,
            index=False,
            sheet_name="Energy KPI"
        )

        df_site.to_excel(
            writer,
            index=False,
            sheet_name="Synthese Site"
        )

        df_daily.to_excel(
            writer,
            index=False,
            sheet_name="Synthese Jour"
        )

    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger Excel",
        data=buffer,
        file_name="dashboard_ge_energy.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


    # =====================================================
# ALIAS POUR COMPATIBILITÉ AVEC app_ge.py
# =====================================================

def show_dashboard_ge():
        show_dashboard()