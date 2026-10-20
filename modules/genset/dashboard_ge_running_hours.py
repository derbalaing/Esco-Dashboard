"""Dashboard GE : visibilité, heures de marche et LOSTCOM sur 10 jours.

Emplacement dans le projet : modules/genset/dashboard_ge_running_hours.py
Dans app.py (ou CamerounTwesco.py) :
    from modules.genset.dashboard_ge_running_hours import show_ge_running_hours_dashboard
    ...
    elif page == "Dashboard GE":
        show_ge_running_hours_dashboard()

PRINCIPES :
- Population = sites avec une installation dans genset_installations.
- 10 jours calendaires, terminant à la dernière date GE importée.
- Toute date manquante ou sans mesure exploitable = jour LOSTCOM.
- 0 h GE avec une mesure reçue = NORMAL (GE à l'arrêt, pas LOSTCOM).
- Sites LOSTCOM, GE >=22 h et GE 18-22 h peuvent se chevaucher :
  les trois indicateurs restent donc indépendants.
- Pas de jointure à solar_kpi_daily (ne pas confondre télémétrie PV et GE).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from config.database import engine


@st.cache_data(ttl=300, show_spinner="Chargement des données GE...")
def load_ge_daily_matrix() -> pd.DataFrame:
    """Une ligne par site GE installé et par date des dix derniers jours.

    On utilise generate_series pour rendre visibles les jours SANS relevé.
    Les valeurs absentes ne sont jamais converties en 0 h GE.
    """
    sql = text("""
        WITH anchor AS (
            SELECT COALESCE(MAX(running_date), CURRENT_DATE)::date AS end_date
            FROM public.ge_running_hours_daily
        ),
        ge_sites AS (
            -- DISTINCT ON évite de doubler les jours si plusieurs lignes
            -- historiques subsistent dans genset_installations.
            SELECT DISTINCT ON (gi.site_id)
                gi.site_id, s.code_site, COALESCE(s.site_name, '-') AS site_name,
                COALESCE(t.team_name, 'Non affectée') AS team_name,
                COALESCE(s.typologie_fms, 'Non défini') AS typologie_fms,
                COALESCE(gi.brand, '-') AS brand,
                COALESCE(gi.model, '-') AS model,
                gi.rated_power_kva,
                COALESCE(gi.status, '-') AS genset_status
            FROM public.genset_installations gi
            JOIN public.sites s ON s.site_id = gi.site_id
            LEFT JOIN public.teams t ON t.team_id = s.team_id
            ORDER BY gi.site_id, gi.updated_at DESC NULLS LAST, gi.genset_id DESC
        ),
        calendar AS (
            SELECT d::date AS running_date
            FROM anchor a,
            generate_series(
                a.end_date - INTERVAL '9 days',
                a.end_date,
                INTERVAL '1 day'
            ) AS series(d)
        ),
        raw_day AS (
            SELECT
                gr.site_id, gr.running_date,
                SUM(gr.running_hours) FILTER (
                    WHERE gr.running_hours IS NOT NULL
                      AND UPPER(TRIM(COALESCE(gr.status, 'NORMAL')))
                          NOT IN ('LOSTCOM', 'INVALID_VALUE')
                ) AS hours_valid,
                COUNT(*) FILTER (
                    WHERE gr.running_hours IS NOT NULL
                      AND UPPER(TRIM(COALESCE(gr.status, 'NORMAL')))
                          NOT IN ('LOSTCOM', 'INVALID_VALUE')
                ) AS valid_measure_count,
                COUNT(*) FILTER (
                    WHERE gr.running_hours IS NULL
                       OR UPPER(TRIM(COALESCE(gr.status, 'NORMAL')))
                          IN ('LOSTCOM', 'INVALID_VALUE')
                ) AS bad_measure_count
            FROM public.ge_running_hours_daily gr
            CROSS JOIN anchor a
            WHERE gr.running_date BETWEEN a.end_date - INTERVAL '9 days' AND a.end_date
            GROUP BY gr.site_id, gr.running_date
        ),
        classified AS (
            SELECT
                gs.*, c.running_date,
                a.end_date AS last_day,
                (a.end_date - INTERVAL '9 days')::date AS start_10_days,
                rd.hours_valid,
                COALESCE(rd.valid_measure_count, 0) AS valid_measure_count,
                COALESCE(rd.bad_measure_count, 0) AS bad_measure_count,
                CASE
                    WHEN rd.site_id IS NULL THEN 'LOSTCOM'
                    WHEN COALESCE(rd.valid_measure_count, 0) = 0 THEN 'LOSTCOM'
                    WHEN COALESCE(rd.bad_measure_count, 0) > 0 THEN 'LOSTCOM'
                    WHEN rd.hours_valid >= 22 THEN 'GE_22H_PLUS'
                    WHEN rd.hours_valid >= 18 THEN 'GE_18_22H'
                    ELSE 'NORMAL'
                END AS day_status,
                CASE
                    WHEN rd.site_id IS NULL THEN 'ABSENT'
                    WHEN COALESCE(rd.valid_measure_count, 0) = 0 THEN 'INEXPLOITABLE'
                    WHEN COALESCE(rd.bad_measure_count, 0) > 0 THEN 'PARTIEL'
                    ELSE 'RECU'
                END AS data_quality
            FROM ge_sites gs
            CROSS JOIN calendar c
            CROSS JOIN anchor a
            LEFT JOIN raw_day rd
              ON rd.site_id = gs.site_id AND rd.running_date = c.running_date
        )
        SELECT
            site_id, code_site, site_name, team_name, typologie_fms,
            brand, model, rated_power_kva, genset_status,
            running_date, last_day, start_10_days,
            CASE WHEN day_status = 'LOSTCOM' THEN NULL
                 ELSE hours_valid END AS running_hours,
            valid_measure_count, bad_measure_count, day_status, data_quality
        FROM classified
        ORDER BY code_site, running_date
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        return df

    for col in ["running_date", "last_day", "start_10_days"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    for col in ["running_hours", "rated_power_kva"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_summary(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Agrégation par site : les métriques GE 22h et LOSTCOM se chevauchent."""
    if df_daily.empty:
        return pd.DataFrame()
    g = df_daily.copy()
    g["valid_day"] = g["day_status"] != "LOSTCOM"
    g["is_lostcom"] = g["day_status"] == "LOSTCOM"
    g["is_no_data"] = g["data_quality"] == "ABSENT"
    g["is_22"] = g["day_status"] == "GE_22H_PLUS"
    g["is_18_22"] = g["day_status"] == "GE_18_22H"
    g["valid_hours"] = g["running_hours"].where(g["valid_day"])

    summary = (
        g.groupby("site_id", as_index=False)
        .agg(
            code_site=("code_site", "first"),
            site_name=("site_name", "first"),
            team_name=("team_name", "first"),
            typologie_fms=("typologie_fms", "first"),
            brand=("brand", "first"),
            model=("model", "first"),
            rated_power_kva=("rated_power_kva", "first"),
            genset_status=("genset_status", "first"),
            days_with_data=("valid_day", "sum"),
            lostcom_days_10j=("is_lostcom", "sum"),
            missing_days_10j=("is_no_data", "sum"),
            days_ge_22h_plus=("is_22", "sum"),
            days_ge_18_22h=("is_18_22", "sum"),
            ge_hours_10j=("valid_hours", "sum"),
            avg_ge_hours_10j=("valid_hours", "mean"),
            max_ge_hours_day=("valid_hours", "max"),
        )
    )
    for col in ["ge_hours_10j", "avg_ge_hours_10j", "max_ge_hours_day"]:
        summary[col] = summary[col].fillna(0)

    summary["ge_status_10j"] = "NORMAL"
    summary.loc[summary["days_ge_18_22h"] > 0, "ge_status_10j"] = "GE_18_22H"
    summary.loc[summary["days_ge_22h_plus"] > 0, "ge_status_10j"] = "GE_22H_PLUS"
    summary.loc[summary["lostcom_days_10j"] > 0, "ge_status_10j"] = "LOSTCOM"
    # Les colonnes days_ge_22h_plus et days_ge_18_22h restent NON exclusives.
    return summary.sort_values(
        ["lostcom_days_10j", "days_ge_22h_plus", "ge_hours_10j"],
        ascending=[False, False, False], kind="stable"
    )


def show_ge_running_hours_dashboard():
    st.title("⚙️ Dashboard GE — Heures de fonctionnement")
    st.caption(
        "Analyse de 10 jours calendaires • Sites avec GE installé • "
        "Absence de relevé = LOSTCOM • 0 h mesurée = GE à l'arrêt (pas LOSTCOM)"
    )
    if st.button("🔄 Actualiser", key="ge_runtime_refresh"):
        load_ge_daily_matrix.clear()
        st.rerun()

    try:
        df_daily = load_ge_daily_matrix()
    except Exception as exc:
        st.error("Impossible de charger le suivi GE. Vérifiez la connexion DB et le script SQL d'initialisation.")
        st.caption(f"Type d’erreur : {type(exc).__name__}. Consultez les logs Streamlit Cloud pour le détail.")
        return
    if df_daily.empty:
        st.warning("Aucun site avec GE installé trouvé dans genset_installations.")
        return

    summary = build_summary(df_daily)
    start_day = df_daily["start_10_days"].iloc[0]
    last_day = df_daily["last_day"].iloc[0]
    st.info(f"Période analysée : **{start_day:%d/%m/%Y} au {last_day:%d/%m/%Y}** (dernière date importée en base).")

    # Filtres qui s'appliquent à tous les indicateurs et graphiques
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        filter_type = st.selectbox(
            "Situation à afficher",
            ["TOUS", "LOSTCOM", "GE ≥ 22h (au moins 1 jour)", "GE 18–22h (au moins 1 jour)", "NORMAL (10 jours)"],
            key="ge_runtime_status_filter"
        )
    with col2:
        team = st.selectbox(
            "Équipe", ["TOUS"] + sorted(summary["team_name"].dropna().astype(str).unique().tolist()),
            key="ge_runtime_team_filter"
        )
    with col3:
        typology = st.selectbox(
            "Typologie", ["TOUS"] + sorted(summary["typologie_fms"].dropna().astype(str).unique().tolist()),
            key="ge_runtime_typology_filter"
        )
    with col4:
        installation_status = st.selectbox(
            "Statut GE installé",
            ["TOUS"] + sorted(summary["genset_status"].dropna().astype(str).unique().tolist()),
            key="ge_runtime_install_status_filter"
        )

    search = st.text_input("🔎 Code site", placeholder="Rechercher un site (ex. CTR_1176)", key="ge_runtime_site_search")
    f = summary.copy()
    if filter_type == "LOSTCOM":
        f = f[f["lostcom_days_10j"] > 0]
    elif filter_type.startswith("GE ≥ 22h"):
        f = f[f["days_ge_22h_plus"] > 0]
    elif filter_type.startswith("GE 18–22h"):
        f = f[f["days_ge_18_22h"] > 0]
    elif filter_type.startswith("NORMAL"):
        f = f[f["ge_status_10j"] == "NORMAL"]
    if team != "TOUS":
        f = f[f["team_name"] == team]
    if typology != "TOUS":
        f = f[f["typologie_fms"] == typology]
    if installation_status != "TOUS":
        f = f[f["genset_status"] == installation_status]
    if search.strip():
        f = f[f["code_site"].astype(str).str.contains(search.strip(), case=False, regex=False, na=False)]

    st.divider()
    a, b, c, d, e, h = st.columns(6)
    a.metric("Sites avec GE", len(f))
    b.metric("Heures GE reçues (10 j)", f"{f['ge_hours_10j'].sum():,.1f} h")
    c.metric("Sites LOSTCOM", int((f["lostcom_days_10j"] > 0).sum()))
    d.metric("GE ≥ 22 h", int((f["days_ge_22h_plus"] > 0).sum()))
    e.metric("GE 18–22 h", int((f["days_ge_18_22h"] > 0).sum()))
    h.metric("Jours LOSTCOM", int(f["lostcom_days_10j"].sum()))
    st.caption("Les KPI LOSTCOM / ≥22 h / 18–22 h ne sont pas exclusifs : un site peut figurer dans plusieurs catégories.")

    filtered_daily = df_daily[df_daily["site_id"].isin(f["site_id"])].copy()
    left, right = st.columns(2)
    with left:
        counts = filtered_daily.groupby(["running_date", "day_status"], as_index=False).size()
        if not counts.empty:
            fig = px.bar(
                counts, x="running_date", y="size", color="day_status",
                barmode="stack", title="État de tous les sites GE par jour",
                labels={"running_date": "Date", "size": "Sites", "day_status": "État"},
            )
            fig.update_layout(height=420, legend_title_text="État du jour")
            st.plotly_chart(fig, use_container_width=True, key="ge_runtime_chart_day_status")
    with right:
        top = f.nlargest(20, "ge_hours_10j").sort_values("ge_hours_10j")
        if not top.empty:
            fig = px.bar(
                top, y="code_site", x="ge_hours_10j", orientation="h",
                title="Top 20 — Heures GE renseignées sur 10 jours",
                labels={"code_site": "Site", "ge_hours_10j": "Heures (h)"},
                text="ge_hours_10j",
            )
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig.update_layout(height=420, yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True, key="ge_runtime_chart_top20")

    st.subheader("📋 Synthèse GE — 10 derniers jours")
    columns = [
        "code_site", "site_name", "team_name", "typologie_fms", "brand", "model",
        "rated_power_kva", "genset_status", "ge_status_10j", "ge_hours_10j",
        "avg_ge_hours_10j", "max_ge_hours_day", "days_with_data",
        "missing_days_10j", "lostcom_days_10j", "days_ge_22h_plus", "days_ge_18_22h"
    ]
    st.dataframe(
        f[columns], use_container_width=True, hide_index=True, height=520,
        column_config={
            "code_site": st.column_config.Column("Code site", pinned=True, width="small"),
            "site_name": st.column_config.Column("Nom site", pinned=True, width="medium"),
            "ge_status_10j": "Statut sur 10 jours",
            "ge_hours_10j": st.column_config.NumberColumn("Heures GE / 10j", format="%.1f"),
            "avg_ge_hours_10j": st.column_config.NumberColumn("Moy. h/j reçu", format="%.1f"),
            "max_ge_hours_day": st.column_config.NumberColumn("Max h/j", format="%.1f"),
            "lostcom_days_10j": "Jours LOSTCOM",
            "missing_days_10j": "Jours absents",
            "days_ge_22h_plus": "Jours ≥22 h",
            "days_ge_18_22h": "Jours 18–22 h",
        },
    )
    st.download_button(
        "⬇️ Export synthèse CSV",
        f[columns].to_csv(index=False).encode("utf-8-sig"),
        file_name="synthese_ge_10_jours.csv", mime="text/csv", key="ge_runtime_export_summary"
    )

    st.subheader("📅 Détail par site et par jour (inclut les jours sans relevé)")
    st.dataframe(
        filtered_daily[[
            "code_site", "running_date", "running_hours", "day_status", "data_quality",
            "valid_measure_count", "bad_measure_count", "team_name"
        ]].sort_values(["code_site", "running_date"], ascending=[True, False]),
        use_container_width=True, hide_index=True, height=450,
        column_config={
            "code_site": st.column_config.Column("Code site", pinned=True, width="small"),
            "running_date": "Date",
            "running_hours": st.column_config.NumberColumn("Heures GE (h)", format="%.2f"),
            "day_status": "Statut jour",
            "data_quality": "Qualité du relevé",
        },
    )
    st.download_button(
        "⬇️ Export détail 10 jours CSV",
        filtered_daily.to_csv(index=False).encode("utf-8-sig"),
        file_name="detail_ge_10_jours.csv", mime="text/csv", key="ge_runtime_export_daily"
    )

    st.caption(
        "Convention : GE ≥ 22 h correspond à une durée journalière d'au moins 22 heures ; "
        "18–22 h signifie 18 h ≤ durée < 22 h. "
        "Une durée absente n'est jamais assimilée à 0 h. "
        "Sur un site équipé de plusieurs GE, la durée du site est la somme des durées de chaque GE."
    )
