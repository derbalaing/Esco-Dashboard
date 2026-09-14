import io

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import text

from config.database import engine


# =====================================================
# DATA
# =====================================================

@st.cache_data(ttl=300)
def load_grid_dates():

    query = text("""
    SELECT DISTINCT
        grid_date
    FROM site_grid
    WHERE grid_date IS NOT NULL
    ORDER BY grid_date DESC
    """)

    df = pd.read_sql(query, engine)

    if df.empty:
        return df

    df["grid_date"] = pd.to_datetime(df["grid_date"]).dt.date

    return df


def load_grid_table(grid_date):

    query = text("""
    SELECT
        s.site_id,
        s.code_site,
        COALESCE(s.site_name, '') AS site_name,
        COALESCE(s.typologie_fms, 'Non défini') AS typologie_fms,

        g.grid_date,

        COALESCE(g.grid_mode, 'NO_GRID_DATA') AS grid_mode,

        g.grid_availability_pct,
        g.grid_outages_per_day,

        COALESCE(g.source, 'NO_DATA') AS source,

        COALESCE(g.status, 'NO_GRID_DATA') AS status,

        g.updated_at

    FROM sites s

    LEFT JOIN site_grid g
        ON g.site_id = s.site_id
        AND g.grid_date = :grid_date

    ORDER BY
        s.code_site
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "grid_date": grid_date
        }
    )

    if df.empty:
        return df

    df["grid_date"] = pd.to_datetime(
        df["grid_date"],
        errors="coerce"
    ).dt.date

    df["grid_availability_pct"] = pd.to_numeric(
        df["grid_availability_pct"],
        errors="coerce"
    )

    df["grid_outages_per_day"] = pd.to_numeric(
        df["grid_outages_per_day"],
        errors="coerce"
    )

    return df




@st.cache_data(ttl=300)
def load_monthly_fuel_for_sites(site_ids):

    if site_ids is None or len(site_ids) == 0:
        return pd.DataFrame()

    site_ids = [
        int(x)
        for x in site_ids
        if pd.notna(x)
    ]

    if len(site_ids) == 0:
        return pd.DataFrame()

    query = text("""
    SELECT
        DATE_TRUNC('month', e.kpi_date)::date AS month_date,

        COUNT(DISTINCT e.site_id) AS sites_simules,
        COUNT(DISTINCT e.kpi_date) AS nb_jours,

        SUM(e.fuel_consumption_l) AS fuel_total_l,

        SUM(e.fuel_consumption_l)
        / NULLIF(COUNT(DISTINCT e.kpi_date), 0) AS fuel_moyen_jour_l,

        AVG(e.fuel_consumption_l) AS fuel_moyen_site_jour_l

    FROM energy_kpi_daily e

    WHERE e.site_id = ANY(:site_ids)

    GROUP BY
        DATE_TRUNC('month', e.kpi_date)

    ORDER BY
        month_date
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "site_ids": site_ids
        }
    )

    if df.empty:
        return df

    df["month_date"] = pd.to_datetime(
        df["month_date"],
        errors="coerce"
    )

    df["mois"] = df["month_date"].dt.strftime("%Y-%m")

    df["fuel_total_l"] = pd.to_numeric(
        df["fuel_total_l"],
        errors="coerce"
    ).fillna(0)

    df["fuel_moyen_jour_l"] = pd.to_numeric(
        df["fuel_moyen_jour_l"],
        errors="coerce"
    ).fillna(0)

    df["fuel_moyen_site_jour_l"] = pd.to_numeric(
        df["fuel_moyen_site_jour_l"],
        errors="coerce"
    ).fillna(0)

    return df



@st.cache_data(ttl=300)
def load_grid_calendar_site(site_id):

    query = text("""
    SELECT
        g.grid_date,
        g.grid_availability_pct,
        COALESCE(g.grid_mode, 'NO_GRID_DATA') AS grid_mode,
        COALESCE(g.status, 'NO_GRID_DATA') AS status,
        COALESCE(g.source, 'NO_DATA') AS source
    FROM site_grid g
    WHERE g.site_id = :site_id
      AND g.grid_date IS NOT NULL
    ORDER BY
        g.grid_date
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "site_id": int(site_id)
        }
    )

    if df.empty:
        return df

    df["grid_date"] = pd.to_datetime(
        df["grid_date"],
        errors="coerce"
    ).dt.date

    df["date"] = pd.to_datetime(
        df["grid_date"],
        errors="coerce"
    )

    df["grid_availability_pct"] = pd.to_numeric(
        df["grid_availability_pct"],
        errors="coerce"
    )

    df["month_key"] = df["date"].dt.strftime("%Y-%m")

    return df

@st.cache_data(ttl=300)
def load_fuel_monthly_comparison(site_ids):

        if site_ids is None or len(site_ids) == 0:
            return pd.DataFrame()

        site_ids = [
            int(x)
            for x in site_ids
            if pd.notna(x)
        ]

        if len(site_ids) == 0:
            return pd.DataFrame()

        query = text("""
        SELECT
            fuel_month,
            code_site,
            site_name,
            typologie_fms,
            actual_fuel_l,
            simulated_fuel_l,
            fuel_gap_l,
            fuel_gap_pct,
            simulated_days,
            simulated_ge_runtime_h,
            source,
            comment
        FROM v_fuel_monthly_comparison
        WHERE site_id = ANY(:site_ids)
        ORDER BY
            fuel_month DESC,
            code_site
        """)

        df = pd.read_sql(
            query,
            engine,
            params={
                "site_ids": site_ids
            }
        )

        if df.empty:
            return df

        df["fuel_month"] = pd.to_datetime(
            df["fuel_month"],
            errors="coerce"
        ).dt.date

        numeric_cols = [
            "actual_fuel_l",
            "simulated_fuel_l",
            "fuel_gap_l",
            "fuel_gap_pct",
            "simulated_days",
            "simulated_ge_runtime_h",
        ]

        for col in numeric_cols:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            ).fillna(0)

        return df


def update_grid_manual(
    site_id,
    grid_date,
    grid_mode,
    grid_availability_pct,
    grid_outages_per_day
):

    sql = text("""
    INSERT INTO site_grid
    (
        site_id,
        grid_date,
        grid_mode,
        grid_availability_pct,
        grid_outages_per_day,
        source,
        status,
        updated_at
    )
    VALUES
    (
        :site_id,
        :grid_date,
        :grid_mode,
        :grid_availability_pct,
        :grid_outages_per_day,
        'MANUAL_EDIT',
        'MODIFIE_MANUEL',
        NOW()
    )
    ON CONFLICT (site_id, grid_date)
    DO UPDATE SET
        grid_mode = EXCLUDED.grid_mode,
        grid_availability_pct = EXCLUDED.grid_availability_pct,
        grid_outages_per_day = EXCLUDED.grid_outages_per_day,
        source = 'MANUAL_EDIT',
        status = 'MODIFIE_MANUEL',
        updated_at = NOW();
    """)

    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "site_id": int(site_id),
                "grid_date": grid_date,
                "grid_mode": grid_mode,
                "grid_availability_pct": grid_availability_pct,
                "grid_outages_per_day": grid_outages_per_day,
            }
        )





def build_grid_availability_calendar(df_calendar, month_key):

    year, month = map(int, month_key.split("-"))

    month_start = pd.Timestamp(
        year=year,
        month=month,
        day=1
    )

    month_end = month_start + pd.offsets.MonthEnd(0)

    all_days = pd.date_range(
        month_start,
        month_end,
        freq="D"
    )

    df_days = pd.DataFrame(
        {
            "date": all_days
        }
    )

    df_days["grid_date"] = df_days["date"].dt.date

    df_days = df_days.merge(
        df_calendar[
            [
                "grid_date",
                "grid_availability_pct",
                "grid_mode",
                "status",
                "source",
            ]
        ],
        on="grid_date",
        how="left"
    )

    df_days["weekday"] = df_days["date"].dt.weekday

    first_weekday = month_start.weekday()

    df_days["week"] = (
        (
            df_days["date"].dt.day
            + first_weekday
            - 1
        )
        // 7
    ).astype(int)

    max_week = int(df_days["week"].max())

    day_names = [
        "Lun",
        "Mar",
        "Mer",
        "Jeu",
        "Ven",
        "Sam",
        "Dim",
    ]

    z = [
        [None for _ in range(7)]
        for _ in range(max_week + 1)
    ]

    text_values = [
        ["" for _ in range(7)]
        for _ in range(max_week + 1)
    ]

    hover_values = [
        ["" for _ in range(7)]
        for _ in range(max_week + 1)
    ]

    for _, r in df_days.iterrows():

        week = int(r["week"])
        weekday = int(r["weekday"])
        day_number = int(r["date"].day)

        availability = r["grid_availability_pct"]
        grid_mode = r.get("grid_mode", "NO_GRID_DATA")
        status = r.get("status", "NO_GRID_DATA")
        source = r.get("source", "NO_DATA")

        if pd.isna(availability):

            z[week][weekday] = None

            text_values[week][weekday] = (
                f"{day_number}<br>-"
            )

            hover_values[week][weekday] = (
                f"Date : {r['grid_date']}<br>"
                f"Disponibilité : N/A<br>"
                f"Mode : {grid_mode}<br>"
                f"Status : {status}<br>"
                f"Source : {source}"
            )

        else:

            availability_value = float(availability)

            z[week][weekday] = availability_value

            text_values[week][weekday] = (
                f"{day_number}<br>{availability_value:.0f}%"
            )

            hover_values[week][weekday] = (
                f"Date : {r['grid_date']}<br>"
                f"Disponibilité : {availability_value:.2f}%<br>"
                f"Mode : {grid_mode}<br>"
                f"Status : {status}<br>"
                f"Source : {source}"
            )

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=day_names,
            y=[
                f"Semaine {i + 1}"
                for i in range(max_week + 1)
            ],
            text=text_values,
            texttemplate="%{text}",
            hovertext=hover_values,
            hoverinfo="text",
            zmin=0,
            zmax=100,
            colorscale="RdYlGn",
            colorbar=dict(
                title="Grid %"
            )
        )
    )

    fig.update_layout(
        title=f"Disponibilité Grid - {month_key}",
        height=420,
        margin=dict(
            l=20,
            r=20,
            t=60,
            b=20
        )
    )

    fig.update_yaxes(
        autorange="reversed"
    )

    return fig

@st.cache_data(ttl=300)
def load_daily_fuel_by_site(site_ids):

    if site_ids is None or len(site_ids) == 0:
        return pd.DataFrame()

    site_ids = [
        int(x)
        for x in site_ids
        if pd.notna(x)
    ]

    if len(site_ids) == 0:
        return pd.DataFrame()

    query = text("""
    SELECT
        e.kpi_date,
        s.site_id,
        s.code_site,
        COALESCE(s.site_name, '') AS site_name,

        e.fuel_consumption_l,
        e.generator_runtime_h,
        e.generator_energy_kwh,
        e.grid_energy_kwh,
        e.solar_energy_kwh,
        e.load_energy_kwh,
        e.soc_start_pct,
        e.soc_final_pct,
        e.unserved_load_kwh

    FROM energy_kpi_daily e

    JOIN sites s
        ON s.site_id = e.site_id

    WHERE e.site_id = ANY(:site_ids)

    ORDER BY
        e.kpi_date DESC,
        s.code_site
    """)

    df = pd.read_sql(
        query,
        engine,
        params={
            "site_ids": site_ids
        }
    )

    if df.empty:
        return df

    df["kpi_date"] = pd.to_datetime(
        df["kpi_date"],
        errors="coerce"
    ).dt.date

    numeric_cols = [
        "fuel_consumption_l",
        "generator_runtime_h",
        "generator_energy_kwh",
        "grid_energy_kwh",
        "solar_energy_kwh",
        "load_energy_kwh",
        "soc_start_pct",
        "soc_final_pct",
        "unserved_load_kwh",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            ).fillna(0)

    return df

# =====================================================
# PAGE GRID
# =====================================================
def show_simulation_fuel():

    st.title("🔌 Analyse Fuel ")

    col_refresh, col_info = st.columns([1, 4])

    with col_refresh:
        if st.button("🔄 Actualiser", key="refresh_grid_dashboard"):
            st.cache_data.clear()
            st.rerun()

    with col_info:
        st.caption("Actualise les données Grid depuis la base.")

    df_dates = load_grid_dates()

    if df_dates.empty:
        st.warning("Aucune date trouvée dans site_grid.")
        return

    selected_date = st.sidebar.selectbox(
        "Date Grid",
        df_dates["grid_date"].tolist(),
        index=0,
        key="grid_dashboard_date"
    )

    df = load_grid_table(selected_date)

    if df.empty:
        st.warning("Aucune donnée Grid trouvée.")
        return

    st.caption(
        f"Tableau Grid pour la date : **{selected_date}**"
    )

    # =====================================================
    # FILTRES
    # =====================================================

    status_options = ["TOUS"] + sorted(
        df["status"].fillna("NO_GRID_DATA").unique().tolist()
    )

    selected_status = st.sidebar.selectbox(
        "Filtre Status",
        status_options,
        index=0,
        key="grid_dashboard_status"
    )

    mode_options = ["TOUS"] + sorted(
        df["grid_mode"].fillna("NO_GRID_DATA").unique().tolist()
    )

    selected_mode = st.sidebar.selectbox(
        "Filtre Grid Mode",
        mode_options,
        index=0,
        key="grid_dashboard_mode"
    )

    typologie_options = ["TOUS"] + sorted(
        df["typologie_fms"].fillna("Non défini").unique().tolist()
    )

    selected_typologie = st.sidebar.selectbox(
        "Filtre Typologie FMS",
        typologie_options,
        index=0,
        key="grid_dashboard_typologie_fms"
    )

    search_site = st.sidebar.text_input(
        "Recherche code site",
        value="",
        key="grid_dashboard_search"
    )

    df_filtered = df.copy()

    if selected_status != "TOUS":
        df_filtered = df_filtered[
            df_filtered["status"] == selected_status
        ].copy()

    if selected_mode != "TOUS":
        df_filtered = df_filtered[
            df_filtered["grid_mode"] == selected_mode
        ].copy()

    if selected_typologie != "TOUS":
        df_filtered = df_filtered[
            df_filtered["typologie_fms"] == selected_typologie
        ].copy()

    if search_site.strip() != "":
        search_value = search_site.strip().upper()

        df_filtered = df_filtered[
            df_filtered["code_site"]
            .astype(str)
            .str.upper()
            .str.contains(search_value, na=False)
        ].copy()

    # =====================================================
    # KPI GRID
    # =====================================================

    total_sites = len(df)
    total_filtered = len(df_filtered)

    on_grid_active_sites = len(
        df[
            (df["grid_mode"].astype(str).str.upper() == "ON_GRID")
            &
            (df["status"].astype(str).str.upper() == "ACTIVE")
        ]
    )

    offgrid_sites = len(
        df[df["grid_mode"].astype(str).str.upper() == "OFF_GRID"]
    )

    lostcom_sites = len(
        df[df["status"].astype(str).str.upper() == "LOSTCOM"]
    )

    no_grid_data = len(
        df[df["status"].astype(str).str.upper() == "NO_GRID_DATA"]
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.metric("Total sites", total_sites)

    with c2:
        st.metric("Filtrés", total_filtered)

    with c3:
        st.metric("ON_GRID actif", on_grid_active_sites)

    with c4:
        st.metric("OFF_GRID", offgrid_sites)

    with c5:
        st.metric("LOSTCOM", lostcom_sites)

    c6, c7, c8 = st.columns(3)

    with c6:
        st.metric("NO GRID DATA", no_grid_data)

    with c7:
        avg_availability = df_filtered["grid_availability_pct"].mean()

        if pd.isna(avg_availability):
            avg_availability = 0

        st.metric(
            "Disponibilité moyenne",
            f"{avg_availability:.1f} %"
        )

    with c8:
        total_outages = df_filtered["grid_outages_per_day"].sum()

        if pd.isna(total_outages):
            total_outages = 0

        st.metric(
            "Total coupures",
            f"{total_outages:.0f}"
        )

    # =====================================================
    # CONSOMMATION FUEL PAR JOUR PAR SITE
    # =====================================================

    st.divider()
    st.subheader("⛽ Consommation fuel par jour par site")

    site_ids_filtered = (
        df_filtered["site_id"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    df_fuel_daily = load_daily_fuel_by_site(
        site_ids_filtered
    )

    if df_fuel_daily.empty:

        st.info(
            "Aucune donnée fuel trouvée dans energy_kpi_daily "
            "pour les sites filtrés."
        )

    else:

        available_kpi_dates = sorted(
            df_fuel_daily["kpi_date"]
            .dropna()
            .unique()
            .tolist()
        )

        if len(available_kpi_dates) == 0:

            st.info("Aucune date KPI disponible pour les données fuel.")

        else:

            col_date1, col_date2 = st.columns(2)

            with col_date1:
                fuel_start_date = st.date_input(
                    "Date début fuel",
                    value=available_kpi_dates[0],
                    min_value=available_kpi_dates[0],
                    max_value=available_kpi_dates[-1],
                    key="grid_fuel_daily_start_date"
                )

            with col_date2:
                fuel_end_date = st.date_input(
                    "Date fin fuel",
                    value=available_kpi_dates[-1],
                    min_value=available_kpi_dates[0],
                    max_value=available_kpi_dates[-1],
                    key="grid_fuel_daily_end_date"
                )

            df_fuel_daily_filtered = df_fuel_daily[
                (df_fuel_daily["kpi_date"] >= fuel_start_date)
                &
                (df_fuel_daily["kpi_date"] <= fuel_end_date)
            ].copy()

            total_fuel_period = df_fuel_daily_filtered[
                "fuel_consumption_l"
            ].sum()

            avg_fuel_site_day = df_fuel_daily_filtered[
                "fuel_consumption_l"
            ].mean()

            max_fuel_site_day = df_fuel_daily_filtered[
                "fuel_consumption_l"
            ].max()

            if pd.isna(avg_fuel_site_day):
                avg_fuel_site_day = 0

            if pd.isna(max_fuel_site_day):
                max_fuel_site_day = 0

            f1, f2, f3 = st.columns(3)

            with f1:
                st.metric(
                    "Fuel total période",
                    f"{total_fuel_period:.1f} L"
                )

            with f2:
                st.metric(
                    "Moyenne site / jour",
                    f"{avg_fuel_site_day:.2f} L"
                )

            with f3:
                st.metric(
                    "Max site / jour",
                    f"{max_fuel_site_day:.1f} L"
                )

            display_fuel_columns = [
                "kpi_date",
                "code_site",
                "site_name",
                "fuel_consumption_l",
                "generator_runtime_h",
                "generator_energy_kwh",
                "grid_energy_kwh",
                "solar_energy_kwh",
                "load_energy_kwh",
                "soc_start_pct",
                "soc_final_pct",
                "unserved_load_kwh",
            ]

            display_fuel_columns = [
                col for col in display_fuel_columns
                if col in df_fuel_daily_filtered.columns
            ]

            st.dataframe(
                df_fuel_daily_filtered[display_fuel_columns],
                use_container_width=True,
                hide_index=True
            )

            st.subheader("📊 Moyenne fuel par site sur la période")

            df_fuel_by_site = (
                df_fuel_daily_filtered
                .groupby(
                    [
                        "code_site",
                        "site_name",
                    ],
                    as_index=False
                )
                .agg(
                    jours_simules=("kpi_date", "nunique"),
                    fuel_total_l=("fuel_consumption_l", "sum"),
                    fuel_moyen_jour_l=("fuel_consumption_l", "mean"),
                    ge_runtime_total_h=("generator_runtime_h", "sum"),
                    ge_runtime_moyen_jour_h=("generator_runtime_h", "mean"),
                )
                .sort_values(
                    "fuel_total_l",
                    ascending=False
                )
            )

            st.dataframe(
                df_fuel_by_site,
                use_container_width=True,
                hide_index=True
            )

    # =====================================================
    # FUEL MOYEN PAR MOIS
    # =====================================================

    st.divider()
    st.subheader("⛽ Consommation fuel moyenne par mois")

    df_fuel_month = load_monthly_fuel_for_sites(
        site_ids_filtered
    )

    if df_fuel_month.empty:

        st.info(
            "Aucune donnée fuel mensuelle trouvée dans energy_kpi_daily "
            "pour les sites filtrés."
        )

    else:

        latest_month = df_fuel_month.iloc[-1]

        m1, m2, m3 = st.columns(3)

        with m1:
            st.metric(
                "Fuel total dernier mois",
                f"{latest_month['fuel_total_l']:.1f} L"
            )

        with m2:
            st.metric(
                "Fuel moyen / jour",
                f"{latest_month['fuel_moyen_jour_l']:.1f} L/j"
            )

        with m3:
            st.metric(
                "Fuel moyen site / jour",
                f"{latest_month['fuel_moyen_site_jour_l']:.2f} L"
            )

        fig_fuel_month = px.bar(
            df_fuel_month,
            x="mois",
            y="fuel_moyen_jour_l",
            text="fuel_moyen_jour_l",
            title="Consommation fuel moyenne journalière par mois",
            labels={
                "mois": "Mois",
                "fuel_moyen_jour_l": "Fuel moyen / jour (L)"
            }
        )

        fig_fuel_month.update_traces(
            texttemplate="%{text:.1f} L",
            textposition="outside"
        )

        fig_fuel_month.update_layout(
            height=420,
            xaxis_title="Mois",
            yaxis_title="Fuel moyen / jour (L)",
            showlegend=False
        )

        st.plotly_chart(
            fig_fuel_month,
            use_container_width=True,
            key="grid_fuel_monthly_average"
        )

        with st.expander("📋 Détail fuel mensuel"):
            st.dataframe(
                df_fuel_month,
                use_container_width=True,
                hide_index=True
            )



    # =====================================================
    # COMPARAISON FUEL REEL VS SIMULATEUR
    # =====================================================

    st.divider()
    st.subheader("⛽ Comparaison fuel réel vs simulateur")

    df_compare_fuel = load_fuel_monthly_comparison(
        site_ids_filtered
    )

    if df_compare_fuel.empty:

        st.info(
            "Aucune donnée fuel réelle importée pour les sites filtrés."
        )

    else:

        month_options = sorted(
            df_compare_fuel["fuel_month"]
            .dropna()
            .unique()
            .tolist(),
            reverse=True
        )

        selected_fuel_month = st.selectbox(
            "Mois de comparaison",
            month_options,
            index=0,
            key="fuel_comparison_month"
        )

        df_compare_month = df_compare_fuel[
            df_compare_fuel["fuel_month"] == selected_fuel_month
        ].copy()

        actual_total = df_compare_month["actual_fuel_l"].sum()
        simulated_total = df_compare_month["simulated_fuel_l"].sum()
        gap_total = actual_total - simulated_total

        if actual_total > 0:
            gap_pct = gap_total / actual_total * 100
        else:
            gap_pct = 0

        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.metric(
                "Fuel réel",
                f"{actual_total:.1f} L"
            )

        with k2:
            st.metric(
                "Fuel simulateur",
                f"{simulated_total:.1f} L"
            )

        with k3:
            st.metric(
                "Écart",
                f"{gap_total:.1f} L"
            )

        with k4:
            st.metric(
                "Écart %",
                f"{gap_pct:.1f} %"
            )

        fig_compare = px.bar(
            df_compare_month,
            x="code_site",
            y=[
                "actual_fuel_l",
                "simulated_fuel_l",
            ],
            barmode="group",
            title="Fuel réel vs fuel simulateur par site",
            labels={
                "code_site": "Site",
                "value": "Fuel (L)",
                "variable": "Type"
            }
        )

        fig_compare.update_layout(
            height=450,
            xaxis_title="Site",
            yaxis_title="Fuel (L)"
        )

        st.plotly_chart(
            fig_compare,
            use_container_width=True,
            key=f"fuel_real_vs_simulated_{selected_fuel_month}"
        )

        df_compare_month = df_compare_month.sort_values(
            "fuel_gap_l",
            ascending=False
        )

        st.dataframe(
            df_compare_month[
                [
                    "fuel_month",
                    "code_site",
                    "site_name",
                    "typologie_fms",
                    "actual_fuel_l",
                    "simulated_fuel_l",
                    "fuel_gap_l",
                    "fuel_gap_pct",
                    "simulated_days",
                    "simulated_ge_runtime_h",
                    "source",
                    "comment",
                ]
            ],
            use_container_width=True,
            hide_index=True
        )



    # =====================================================
    # CALENDRIER DISPONIBILITE GRID PAR SITE
    # =====================================================

    st.divider()
    st.subheader("📅 Calendrier disponibilité Grid par site")

    df_sites_calendar = df_filtered[
        [
            "site_id",
            "code_site",
            "site_name",
        ]
    ].drop_duplicates().copy()

    df_sites_calendar["site_label"] = (
        df_sites_calendar["code_site"].astype(str)
        + " - "
        + df_sites_calendar["site_name"].astype(str)
    )

    df_sites_calendar = df_sites_calendar.sort_values(
        "code_site"
    )

    if df_sites_calendar.empty:

        st.warning("Aucun site disponible pour le calendrier.")

    else:

        selected_site_label = st.selectbox(
            "Sélectionner un site",
            df_sites_calendar["site_label"].tolist(),
            key="grid_calendar_site"
        )

        selected_site_id = int(
            df_sites_calendar[
                df_sites_calendar["site_label"] == selected_site_label
            ]["site_id"].iloc[0]
        )

        df_calendar = load_grid_calendar_site(
            selected_site_id
        )

        if df_calendar.empty:

            st.warning(
                "Aucune donnée historique Grid trouvée pour ce site."
            )

        else:

            month_options = sorted(
                df_calendar["month_key"]
                .dropna()
                .unique()
                .tolist()
            )

            selected_month = st.selectbox(
                "Mois",
                month_options,
                index=len(month_options) - 1,
                key="grid_calendar_month"
            )

            fig_calendar = build_grid_availability_calendar(
                df_calendar,
                selected_month
            )

            st.plotly_chart(
                fig_calendar,
                use_container_width=True,
                key=f"grid_availability_calendar_{selected_site_id}_{selected_month}"
            )

    # =====================================================
    # TABLEAU AVEC MODIFICATION MANUELLE
    # =====================================================

    st.divider()
    st.subheader("📋 Liste complète des sites Grid")

    df_table = df_filtered.copy()

    if "Modifier" not in df_table.columns:
        df_table.insert(
            0,
            "Modifier",
            False
        )

    display_columns = [
        "Modifier",
        "code_site",
        "site_name",
        "projet",
        "typologie_fms",
        "grid_date",
        "grid_mode",
        "grid_availability_pct",
        "grid_outages_per_day",
        "source",
        "status",
        "updated_at",
    ]

    available_columns = [
        col for col in display_columns
        if col in df_table.columns
    ]

    edited_df = st.data_editor(
        df_table[available_columns],
        use_container_width=True,
        hide_index=True,
        disabled=[
            col for col in available_columns
            if col != "Modifier"
        ],
        column_config={
            "Modifier": st.column_config.CheckboxColumn(
                "Modifier",
                help="Cocher une seule ligne pour modifier les données Grid",
                default=False
            )
        },
        key=f"grid_manual_edit_table_{selected_date}"
    )

    selected_rows = edited_df[
        edited_df["Modifier"] == True
    ].copy()

    if len(selected_rows) > 1:

        st.warning("Merci de sélectionner une seule ligne à modifier.")

    elif len(selected_rows) == 1:

        selected_code_site = selected_rows.iloc[0]["code_site"]

        original_row = df[
            df["code_site"] == selected_code_site
        ].iloc[0]

        st.markdown("---")
        st.subheader(f"✏️ Modification manuelle Grid : {selected_code_site}")

        current_mode = str(
            original_row.get("grid_mode", "ON_GRID")
        ).upper().strip()

        mode_list = [
            "ON_GRID",
            "OFF_GRID",
            "LOSTCOM",
        ]

        if current_mode not in mode_list:
            current_mode = "ON_GRID"

        with st.form(
            key=f"manual_grid_form_{selected_code_site}_{selected_date}"
        ):

            col1, col2, col3 = st.columns(3)

            with col1:
                new_grid_mode = st.selectbox(
                    "Grid mode",
                    mode_list,
                    index=mode_list.index(current_mode)
                )

            with col2:
                current_availability = original_row.get(
                    "grid_availability_pct"
                )

                if pd.isna(current_availability):
                    current_availability = 0

                new_availability = st.number_input(
                    "Disponibilité Grid (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(current_availability),
                    step=0.01
                )

            with col3:
                current_outages = original_row.get(
                    "grid_outages_per_day"
                )

                if pd.isna(current_outages):
                    current_outages = 0

                new_outages = st.number_input(
                    "Nombre de coupures / jour",
                    min_value=0,
                    value=int(current_outages),
                    step=1
                )

            st.info(
                "Après sauvegarde, le status sera automatiquement "
                "changé vers MODIFIE_MANUEL."
            )

            submitted = st.form_submit_button(
                "💾 Enregistrer la modification"
            )

            if submitted:

                if new_grid_mode == "LOSTCOM":
                    final_availability = None
                    final_outages = None

                elif new_grid_mode == "OFF_GRID":
                    final_availability = 0
                    final_outages = 0

                else:
                    final_availability = float(new_availability)
                    final_outages = int(new_outages)

                update_grid_manual(
                    site_id=int(original_row["site_id"]),
                    grid_date=pd.to_datetime(selected_date).date(),
                    grid_mode=new_grid_mode,
                    grid_availability_pct=final_availability,
                    grid_outages_per_day=final_outages
                )

                st.success(
                    f"✅ Site {selected_code_site} modifié manuellement."
                )

                st.cache_data.clear()
                st.rerun()

    # =====================================================
    # EXPORT EXCEL
    # =====================================================

    buffer = io.BytesIO()

    df_export = df_filtered.copy()

    export_columns = [
        "code_site",
        "site_name",
        "projet",
        "typologie_fms",
        "grid_date",
        "grid_mode",
        "grid_availability_pct",
        "grid_outages_per_day",
        "source",
        "status",
        "updated_at",
    ]

    export_columns = [
        col for col in export_columns
        if col in df_export.columns
    ]

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        df_export[export_columns].to_excel(
            writer,
            index=False,
            sheet_name="Grid Sites"
        )

    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger tableau Grid",
        data=buffer,
        file_name=f"grid_sites_{selected_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"download_grid_sites_{selected_date}"
    )




