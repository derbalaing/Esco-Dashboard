"""DailyAnalyst — Suivi des interventions terrain V2 + Export Excel.

Pre-requis : executer 01_suivi_interventions_supabase.sql (V1), puis
01_mise_a_jour_interventions_v2.sql (V2), dans la meme base Supabase.

Copier ce fichier dans modules/project/dashboard_interventions.py.
Depuis l'application appeler show_interventions_dashboard().
"""

from __future__ import annotations

import hmac
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text
from config.database import engine

TIMEZONE = "Africa/Douala"

# Noms des familles de choix : leurs VALEURS sont gerees dans Supabase.
CATEGORIES = {
    "INTERVENTION_TYPE": "Nature d'intervention",
    "SITE_STATE": "Etat de site",
    "GENSET_TYPE": "Type de GE",
    "GENSET_MODEL": "Modele GE",
    "POWERCORE_TYPE": "Type PowerCore",
    "POWERCORE_MODEL": "Modele PowerCore",
    "BATTERY_TYPE": "Battery Type",
    "BATTERY_CHEMISTRY": "Lithium / ACID",
    "PV_TYPE": "Type de panneaux solaires (PVs)",
}


def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def execute_sql(query: str, params: dict | None = None) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(query), params or {})


def sites_df():
    return read_sql("""
        SELECT site_id, code_site, COALESCE(site_name, '') AS site_name
        FROM public.sites ORDER BY code_site
    """)


def teams_df():
    return read_sql("""
        SELECT team_id, team_name FROM public.teams ORDER BY team_name
    """)


def technicians_df(active_only=True):
    return read_sql("""
        SELECT technician_id, full_name, contact_number, team_id, is_active
        FROM public.intervention_technicians
        WHERE (NOT :active_only OR is_active = TRUE)
        ORDER BY full_name, contact_number
    """, {"active_only": active_only})


def lookup_values(category: str, include_inactive=False) -> list[str]:
    df = read_sql("""
        SELECT option_value FROM public.intervention_lookup_options
        WHERE category=:category AND (is_active=TRUE OR :all_options)
        ORDER BY sort_order, option_value
    """, {"category": category, "all_options": include_inactive})
    return df["option_value"].astype(str).tolist()


def selectable_lookup(label: str, category: str, default=None, key=None, required=False):
    """Choix BDD + valeur historique meme si desactivee, pour ne rien perdre."""
    choices = lookup_values(category)
    if default is not None and str(default).strip() and default not in choices:
        choices = [str(default)] + choices
    choices = list(dict.fromkeys(choices))
    if not required:
        choices = [None] + choices
    if not choices:
        st.warning(f"Aucune valeur configurée pour {label}. Ajoutez-en dans Administration.")
        return None
    initial = default if default in choices else choices[0]
    return st.selectbox(label, choices, index=choices.index(initial),
                        format_func=lambda x: "— Non renseigné —" if x is None else str(x),
                        key=key)


def num_default(row: dict, field: str):
    value = row.get(field)
    return None if value is None or pd.isna(value) else max(0, int(value))


def float_default(row: dict, field: str):
    value = row.get(field)
    return None if value is None or pd.isna(value) else max(0.0, float(value))


def text_default(row: dict, field: str):
    value = row.get(field)
    return "" if value is None or pd.isna(value) else str(value)


def safe_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def format_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    result = df.copy()
    for col in cols:
        if col in result.columns:
            dt = pd.to_datetime(result[col], errors="coerce", utc=True)
            result[col] = dt.dt.tz_convert(TIMEZONE).dt.strftime("%d/%m/%Y %H:%M")
    return result



# ============================================================
# EXPORT EXCEL FORMATE — SUPERVISION ET INTERVENTIONS
# ============================================================

# Mapping des champs de la vue de supervision vers des libelles lisibles.
EXPORT_COL_LABELS = {
    "code_site": "Code site",
    "site_name": "Nom du site",
    "presence_status": "Présence terrain",
    "active_interventions": "Équipes / interventions présentes",
    "teams_on_site": "Équipes sur site",
    "technicians_on_site": "Techniciens sur site",
    "first_arrival_at": "Première arrivée",
    "last_departure_at": "Dernier départ",
    "last_departure_comment": "Commentaire de départ",
    "site_state": "État du site",
    "powercore_type": "Type PowerCore",
    "powercore_model": "Modèle PowerCore",
    "rectifier_count": "Redresseurs installés",
    "rectifier_out_of_service": "Redresseurs hors production",
    "solar_charger_count": "Chargeurs solaires installés",
    "solar_charger_out_of_service": "Chargeurs solaires hors production",
    "powercore_comment": "Remarque PowerCore",
    "genset_type": "Type de GE",
    "genset_model": "Modèle GE",
    "genset_power_kva": "Puissance GE (kVA)",
    "genset_comment": "Remarque GE",
    "battery_type": "Type batterie",
    "battery_chemistry": "Lithium / ACID",
    "battery_element_count": "Nombre éléments batteries",
    "battery_comment": "Remarque batteries",
    "pv_panel_type": "Type de panneaux PV",
    "pv_panel_count": "Nombre de panneaux PV",
    "solar_comment": "Remarque installation solaire",
    "solar_extension_possible": "Extension solaire possible ?",
    "solar_extension_comment": "Commentaire extension solaire",
    "last_technical_update_at": "Dernière mise à jour technique",
    "last_reporting_technician": "Dernier technicien intervenant",
    "last_reporting_contact": "Contact du dernier technicien",
    "intervention_id": "N° intervention",
    "team_name": "Équipe",
    "technician_name": "Technicien",
    "technician_phone": "Contact technicien",
    "intervention_type": "Nature de l'intervention",
    "intervention_status": "Statut intervention",
    "arrival_at": "Arrivée",
    "departure_at": "Départ",
    "elapsed_hours": "Durée sur site (h)",
    "delay_status": "Suivi du délai",
    "arrival_comment": "Commentaire d'arrivée",
    "departure_comment": "Commentaire de départ",
    "report_updated_at": "Dernier relevé technique",
}

EXPORT_DATE_FIELDS = {
    "first_arrival_at", "last_departure_at", "last_technical_update_at",
    "arrival_at", "departure_at", "report_updated_at",
}


def prepare_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Conserve les types Excel, et convertit les timestamps en heure Cameroun."""
    result = df.copy()
    for col in EXPORT_DATE_FIELDS.intersection(result.columns):
        # Les colonnes d'interventions sont stockées en TIMESTAMPTZ PostgreSQL.
        parsed = pd.to_datetime(result[col], errors="coerce", utc=True)
        result[col] = parsed.dt.tz_convert(TIMEZONE).dt.tz_localize(None)
    # Ne pas transformer les valeurs manquantes d'inventaire en zéro.
    result = result.rename(columns=EXPORT_COL_LABELS)
    return result


@st.cache_data(ttl=90, show_spinner=False)
def export_interventions_xlsx(
    sites_data: pd.DataFrame,
    active_data: pd.DataFrame,
    history_data: pd.DataFrame,
    filter_description: str,
) -> bytes:
    """Fichier XLSX multi-feuilles, formaté et utilisable hors connexion."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    sites_data = prepare_export_dataframe(sites_data)
    active_data = prepare_export_dataframe(active_data)
    history_data = prepare_export_dataframe(history_data)

    buffer = BytesIO()
    with pd.ExcelWriter(
        buffer,
        engine="xlsxwriter",
        datetime_format="dd/mm/yyyy hh:mm",
        date_format="dd/mm/yyyy",
        engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}},
    ) as writer:
        book = writer.book
        navy = "#15263E"
        teal = "#087E8B"
        pale = "#E9F5F5"
        gray = "#64748B"
        white = "#FFFFFF"
        title_fmt = book.add_format({"bold": True, "font_size": 17, "font_color": white,
                                     "bg_color": navy, "valign": "vcenter"})
        sub_fmt = book.add_format({"font_size": 10, "font_color": gray})
        head_fmt = book.add_format({"bold": True, "font_color": white, "bg_color": navy,
                                    "border": 1, "border_color": "#B7C8D6", "align": "center",
                                    "valign": "vcenter", "text_wrap": True})
        section_fmt = book.add_format({"bold": True, "font_color": white,
                                       "bg_color": teal, "valign": "vcenter"})
        num_fmt = book.add_format({"num_format": "#,##0", "valign": "top"})
        dec_fmt = book.add_format({"num_format": "#,##0.0", "valign": "top"})
        date_fmt = book.add_format({"num_format": "dd/mm/yyyy hh:mm", "valign": "top"})
        stripe_fmt = book.add_format({"bg_color": "#F2F7FA"})
        green_fmt = book.add_format({"bg_color": "#D7F4E4", "font_color": "#08643E", "bold": True})
        amber_fmt = book.add_format({"bg_color": "#FFF0C2", "font_color": "#875A00", "bold": True})
        red_fmt = book.add_format({"bg_color": "#FFE0E0", "font_color": "#9C1822", "bold": True})
        neutral_fmt = book.add_format({"bg_color": "#EBEFF5", "font_color": "#46556B"})
        notice_fmt = book.add_format({"italic": True, "font_color": gray, "bg_color": pale,
                                      "text_wrap": True, "valign": "vcenter"})
        card_label = book.add_format({"bold": True, "font_size": 10,
                                      "font_color": navy, "bg_color": pale,
                                      "align": "center", "valign": "vcenter"})
        card_value = book.add_format({"bold": True, "font_size": 20,
                                      "font_color": teal, "align": "center", "valign": "vcenter",
                                      "bottom": 2, "bottom_color": "#D1E4E7"})

        def add_data_sheet(name: str, data: pd.DataFrame, summary_text: str,
                           freeze_first_columns: int = 1):
            """Feuille lisible : colonnes dimensionnées, en-têtes fixes et filtres."""
            ws = book.add_worksheet(name)
            writer.sheets[name] = ws
            ncols = max(len(data.columns), 1)
            ws.merge_range(0, 0, 1, min(max(ncols - 1, 1), 7),
                           f"DAILYANALYST  |  {name.upper()}", title_fmt)
            ws.set_row(0, 24)
            ws.set_row(1, 19)
            ws.merge_range(2, 0, 2, min(max(ncols - 1, 1), 7),
                           f"Export : {now:%d/%m/%Y %H:%M} (Douala)  |  {summary_text}", sub_fmt)
            ws.merge_range(3, 0, 3, min(max(ncols - 1, 1), 7),
                           "Champ vide = information non renseignée ; ne pas interpréter comme 0.", notice_fmt)
            ws.set_row(3, 24)
            header_row = 5
            if ncols > 0:
                data.to_excel(writer, sheet_name=name, index=False, startrow=header_row)
                for idx, label in enumerate(data.columns):
                    ws.write(header_row, idx, label, head_fmt)
                    lower = label.lower()
                    if any(tok in lower for tok in ("commentaire", "remarque", "modèle")):
                        width = 37
                    elif any(tok in lower for tok in ("technicien", "équipe", "type de", "nature")):
                        width = 28
                    elif any(tok in lower for tok in ("date", "arrivée", "départ", "mise à jour", "relevé")):
                        width = 23
                    elif any(tok in lower for tok in ("nombre", "installé", "production", "puissance", "(kva)", "durée")):
                        width = 19
                    else:
                        width = min(27, max(16, len(label) + 3))
                    col_format = date_fmt if label in (
                        "Première arrivée", "Dernier départ", "Dernière mise à jour technique",
                        "Arrivée", "Départ", "Dernier relevé technique"
                    ) else dec_fmt if label in ("Puissance GE (kVA)", "Durée sur site (h)") else None
                    ws.set_column(idx, idx, width, col_format)
                ws.set_row(header_row, 36)
                ws.freeze_panes(header_row + 1, min(freeze_first_columns, ncols))
                ws.autofilter(header_row, 0, header_row + max(len(data), 0), ncols - 1)
                ws.hide_gridlines(2)
                ws.set_landscape()
                ws.fit_to_pages(1, 0)
                ws.repeat_rows(header_row)
                ws.set_footer("&CDailyAnalyst · &P / &N")
                if len(data):
                    last = header_row + len(data)
                    ws.conditional_format(header_row + 1, 0, last, ncols - 1,
                                          {"type": "formula", "criteria": "=MOD(ROW(),2)=0", "format": stripe_fmt})
                    statuses = {
                        "Présence terrain": {
                            "SUR_SITE": green_fmt, "A_QUITTE_SITE": amber_fmt,
                            "AUCUNE_INTERVENTION": neutral_fmt,
                        },
                        "État du site": {
                            "UP": green_fmt, "DEGRADE": amber_fmt,
                            "DOWN": red_fmt, "NON_VERIFIE": neutral_fmt,
                        },
                        "Statut intervention": {
                            "ON_SITE": green_fmt, "COMPLETED": neutral_fmt,
                        },
                        "Suivi du délai": {
                            "EN_RETARD_24H": red_fmt, "EN_COURS": green_fmt,
                        },
                        "Extension solaire possible ?": {
                            "OUI": green_fmt, "NON_VERIFIE": neutral_fmt,
                        },
                    }
                    for header, cases in statuses.items():
                        if header in data.columns:
                            index = data.columns.get_loc(header)
                            for keyword, fmt in cases.items():
                                ws.conditional_format(header_row + 1, index, last, index,
                                    {"type": "text", "criteria": "containing", "value": keyword,
                                     "format": fmt})
                    for bad in ("Redresseurs hors production", "Chargeurs solaires hors production"):
                        if bad in data.columns:
                            index = data.columns.get_loc(bad)
                            ws.conditional_format(header_row + 1, index, last, index,
                                {"type": "cell", "criteria": ">", "value": 0, "format": red_fmt})
            return ws

        # 1 — Feuille de synthèse : indicateurs calculés sur le périmètre exporté.
        syn = book.add_worksheet("Synthese")
        writer.sheets["Synthese"] = syn
        syn.hide_gridlines(2)
        syn.set_column("A:A", 4)
        syn.set_column("B:I", 17)
        syn.set_column("J:J", 4)
        syn.merge_range("B2:I3", "DAILYANALYST  |  ÉTAT DES SITES & INTERVENTIONS", title_fmt)
        syn.set_row(1, 25)
        syn.set_row(2, 26)
        syn.merge_range("B5:I5", f"Édité le {now:%d/%m/%Y à %H:%M} · Heure locale : Douala", sub_fmt)
        syn.merge_range("B6:I6", f"Périmètre : {filter_description}", sub_fmt)
        syn.merge_range("B8:I8", "INDICATEURS DE LA SUPERVISION", section_fmt)
        syn.set_row(7, 26)
        n_sites = len(sites_data)
        presence_counts = sites_data.get("Présence terrain", pd.Series(dtype=str)).value_counts()
        state_counts = sites_data.get("État du site", pd.Series(dtype=str)).value_counts()
        interventions = pd.to_numeric(sites_data.get("Équipes / interventions présentes", pd.Series(dtype=float)),
                                      errors="coerce").fillna(0).sum()
        tech_known = sites_data.get("Dernière mise à jour technique", pd.Series(dtype=object)).notna().sum()
        values = [
            ("Sites suivis", n_sites),
            ("Sites avec équipe", int(presence_counts.get("SUR_SITE", 0))),
            ("Interventions ouvertes", int(interventions)),
            ("Fiches techniques", int(tech_known)),
            ("Sites DOWN", int(state_counts.get("DOWN", 0))),
            ("Sites dégradés", int(state_counts.get("DEGRADE", 0))),
        ]
        coords = [("B10:D10", "B11:D12"), ("E10:G10", "E11:G12"),
                  ("B14:D14", "B15:D16"), ("E14:G14", "E15:G16"),
                  ("B18:D18", "B19:D20"), ("E18:G18", "E19:G20")]
        for (label, value), (label_range, value_range) in zip(values, coords):
            syn.merge_range(label_range, label, card_label)
            syn.merge_range(value_range, value, card_value)
        syn.merge_range("B23:D23", "PRÉSENCE TERRAIN", section_fmt)
        syn.merge_range("F23:H23", "ÉTAT TECHNIQUE", section_fmt)
        for i, category in enumerate(("SUR_SITE", "A_QUITTE_SITE", "AUCUNE_INTERVENTION"), start=24):
            syn.write(i, 1, category)
            syn.write_number(i, 3, int(presence_counts.get(category, 0)), num_fmt)
        for i, category in enumerate(("UP", "DEGRADE", "DOWN", "NON_VERIFIE"), start=24):
            syn.write(i, 5, category)
            syn.write_number(i, 7, int(state_counts.get(category, 0)), num_fmt)
        syn.merge_range("B31:I32",
            "Attention : les valeurs manquantes des inventaires ne sont pas des équipements à zéro. "
            "Les feuilles détaillées suivent les filtres de supervision au moment de l'export.", notice_fmt)
        syn.set_row(30, 25)
        syn.set_row(31, 25)
        syn.set_footer("&CDailyAnalyst · &P / &N")

        # 2 — État technique par site, issu de la vue Supabase existante.
        add_data_sheet("Etat des sites", sites_data,
                       f"{len(sites_data)} sites · {filter_description}", freeze_first_columns=2)
        # 3 — Les techniciens déclarés présents sur les sites visibles.
        add_data_sheet("Equipes sur site", active_data,
                       f"{len(active_data)} techniciens actuellement sur site")
        # 4 — Dernières 2000 visites au maximum, restreintes aux sites visibles.
        add_data_sheet("Historique", history_data,
                       f"{len(history_data)} interventions · 2 000 dernières au maximum")

    buffer.seek(0)
    return buffer.getvalue()


@st.cache_data(ttl=120, show_spinner=False)
def load_intervention_history() -> pd.DataFrame:
    """Historique plafonné pour éviter un export trop lourd en cloud."""
    return read_sql("""
        SELECT i.intervention_id, s.code_site, s.site_name,
               COALESCE(t.team_name, 'Non affectée') AS team_name,
               i.technician_name, i.technician_phone, i.intervention_type,
               i.intervention_status, i.arrival_at, i.departure_at,
               i.arrival_comment, i.departure_comment,
               r.site_state, r.powercore_type, r.powercore_model,
               r.rectifier_count, r.rectifier_out_of_service,
               r.solar_charger_count, r.solar_charger_out_of_service,
               r.powercore_comment,
               r.genset_type, r.genset_model, r.genset_power_kva, r.genset_comment,
               r.battery_type, r.battery_chemistry, r.battery_element_count, r.battery_comment,
               r.pv_panel_type, r.pv_panel_count, r.solar_comment,
               r.solar_extension_possible, r.solar_extension_comment,
               r.updated_at AS report_updated_at
        FROM public.site_interventions i
        JOIN public.sites s ON s.site_id=i.site_id
        LEFT JOIN public.teams t ON t.team_id=i.team_id
        LEFT JOIN public.site_technical_reports r ON r.intervention_id=i.intervention_id
        ORDER BY i.arrival_at DESC LIMIT 2000
    """)


def list_active_interventions():
    return read_sql("""
        SELECT i.intervention_id, i.site_id, i.team_id, i.technician_id,
               s.code_site, s.site_name,
               COALESCE(t.team_name,'Non affectée') AS team_name,
               i.technician_name, i.technician_phone,
               i.intervention_type, i.arrival_at, i.arrival_comment,
               ROUND((EXTRACT(EPOCH FROM (NOW() - i.arrival_at))/3600)::numeric, 1)
                   AS elapsed_hours,
               CASE WHEN i.arrival_at < NOW()-INTERVAL '24 hours'
                    THEN 'EN_RETARD_24H' ELSE 'EN_COURS' END AS delay_status
        FROM public.site_interventions i
        JOIN public.sites s ON s.site_id=i.site_id
        LEFT JOIN public.teams t ON t.team_id=i.team_id
        WHERE i.intervention_status='ON_SITE'
        ORDER BY i.arrival_at DESC, i.intervention_id DESC
    """)


def kpis_interventions():
    return read_sql("""
        SELECT
          COUNT(*) FILTER (WHERE (arrival_at AT TIME ZONE 'Africa/Douala')::date
                                   = (NOW() AT TIME ZONE 'Africa/Douala')::date)
                AS arrivals_today,
          COUNT(*) FILTER (WHERE intervention_status='ON_SITE') AS ongoing,
          COUNT(*) FILTER (WHERE intervention_status='COMPLETED') AS closed_total,
          COUNT(*) FILTER (WHERE intervention_status='ON_SITE'
                             AND arrival_at < NOW()-INTERVAL '24 hours') AS overdue_24h
        FROM public.site_interventions
    """).iloc[0]


def intervention_day_df():
    return read_sql("""
        SELECT i.intervention_id, s.code_site, s.site_name,
               COALESCE(t.team_name,'Non affectée') AS team_name,
               i.technician_name, i.technician_phone, i.intervention_type,
               i.arrival_at, i.departure_at,
               CASE WHEN i.intervention_status='ON_SITE' THEN 'SUR_SITE'
                    ELSE 'A_QUITTE_SITE' END AS presence,
               CASE WHEN i.intervention_status='ON_SITE'
                          AND i.arrival_at < NOW()-INTERVAL '24 hours'
                    THEN 'NON_CLOTUREE_24H'
                    WHEN i.intervention_status='ON_SITE' THEN 'EN_COURS'
                    ELSE 'CLOTUREE' END AS suivi
        FROM public.site_interventions i
        JOIN public.sites s ON s.site_id=i.site_id
        LEFT JOIN public.teams t ON t.team_id=i.team_id
        WHERE (i.arrival_at AT TIME ZONE 'Africa/Douala')::date
                  = (NOW() AT TIME ZONE 'Africa/Douala')::date
        ORDER BY i.arrival_at DESC
    """)


def begin_visit(site_id: int, team_id: int | None, technician_id: int,
                nature: str, comment: str):
    with engine.begin() as conn:
        tech = conn.execute(text("""
            SELECT technician_id, full_name, contact_number
            FROM public.intervention_technicians
            WHERE technician_id=:id AND is_active=TRUE
        """), {"id": technician_id}).mappings().first()
        if not tech:
            raise ValueError("Technicien absent de l'annuaire ou désactivé.")
        exists = conn.execute(text("""
            SELECT intervention_id FROM public.site_interventions
            WHERE site_id=:site_id AND intervention_status='ON_SITE'
              AND (technician_id=:tech_id
                   OR LOWER(TRIM(technician_name))=LOWER(TRIM(:name)))
            LIMIT 1
        """), {"site_id": site_id, "tech_id": technician_id,
                 "name": tech["full_name"]}).first()
        if exists:
            raise ValueError("Une intervention est déjà ouverte pour ce technicien sur ce site.")
        new_id = conn.execute(text("""
            INSERT INTO public.site_interventions
                (site_id, team_id, technician_id, technician_name,
                 technician_phone, intervention_type, intervention_status, arrival_comment)
            VALUES (:site_id, :team_id, :tech_id, :name, :phone, :nature, 'ON_SITE', :comment)
            RETURNING intervention_id
        """), {
            "site_id": site_id, "team_id": team_id,
            "tech_id": technician_id, "name": tech["full_name"],
            "phone": tech["contact_number"], "nature": nature,
            "comment": safe_text(comment)
        }).scalar_one()
    return new_id


def latest_report(intervention_id: int, site_id: int) -> dict:
    df = read_sql("""
        SELECT r.* FROM public.site_technical_reports r
        JOIN public.site_interventions i ON i.intervention_id=r.intervention_id
        WHERE r.intervention_id=:id OR i.site_id=:site
        ORDER BY CASE WHEN r.intervention_id=:id THEN 0 ELSE 1 END,
                 r.updated_at DESC, r.report_id DESC
        LIMIT 1
    """, {"id": intervention_id, "site": site_id})
    return {} if df.empty else df.iloc[0].to_dict()


def save_technical_report(intervention_id: int, report: dict):
    cols = [
        "site_state", "powercore_type", "powercore_model", "rectifier_count",
        "solar_charger_count", "rectifier_out_of_service", "solar_charger_out_of_service",
        "powercore_comment", "genset_type", "genset_model", "genset_power_kva",
        "genset_comment", "battery_type", "battery_chemistry", "battery_element_count",
        "battery_comment", "pv_panel_type", "pv_panel_count", "solar_comment",
        "solar_extension_possible", "solar_extension_comment",
    ]
    placeholders = ", ".join(":" + c for c in cols)
    set_sql = ",\n".join(f"{col}=EXCLUDED.{col}" for col in cols)
    query = f"""
        INSERT INTO public.site_technical_reports
            (intervention_id, {', '.join(cols)})
        VALUES (:intervention_id, {placeholders})
        ON CONFLICT (intervention_id) DO UPDATE SET
            {set_sql}, updated_at=NOW()
    """
    with engine.begin() as conn:
        active = conn.execute(text("""
            SELECT 1 FROM public.site_interventions
            WHERE intervention_id=:id AND intervention_status='ON_SITE'
            FOR UPDATE
        """), {"id": intervention_id}).first()
        if not active:
            raise ValueError("L'intervention est clôturée ou introuvable.")
        conn.execute(text(query), {"intervention_id": intervention_id, **report})


def end_visit(intervention_id: int, comment: str):
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE public.site_interventions
            SET intervention_status='COMPLETED', departure_at=NOW(),
                departure_comment=:comment, updated_at=NOW()
            WHERE intervention_id=:id AND intervention_status='ON_SITE'
            RETURNING intervention_id
        """), {"id": intervention_id, "comment": comment.strip()}).first()
        if not result:
            raise ValueError("L'intervention est déjà clôturée ou introuvable.")


def flash(text_message: str):
    st.session_state["interventions_flash_v2"] = text_message
    st.rerun()


@st.fragment(run_every="20s")
def arrival_kpi_and_table():
    """Affiché juste SOUS le formulaire d'arrivée, sans rafraîchir le formulaire."""
    st.divider()
    st.subheader("📊 Suivi des arrivées et interventions")
    kpi = kpis_interventions()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Interventions aujourd'hui", int(kpi["arrivals_today"]))
    c2.metric("Interventions en cours", int(kpi["ongoing"]))
    c3.metric("Interventions clôturées (total)", int(kpi["closed_total"]))
    c4.metric("Non clôturées > 24 h", int(kpi["overdue_24h"]))
    st.caption("Aujourd'hui = date locale du Cameroun · Rafraîchissement toutes les 20 secondes")

    st.markdown("**Techniciens actuellement sur site**")
    active = list_active_interventions()
    if active.empty:
        st.info("Aucun technicien n'est actuellement déclaré sur site.")
    else:
        cols = ["intervention_id", "code_site", "team_name", "technician_name",
                "technician_phone", "intervention_type", "arrival_at", "elapsed_hours", "delay_status"]
        table = format_dates(active[cols], ["arrival_at"])
        st.dataframe(table, use_container_width=True, hide_index=True, height=320,
                     column_config={
                         "code_site": st.column_config.TextColumn("Code site", pinned=True),
                         "technician_name": "Technicien / Team leader",
                         "technician_phone": "Contact",
                         "arrival_at": "Date/heure d'arrivée",
                         "elapsed_hours": "Durée sur site (h)",
                         "delay_status": "État / délai",
                     })
    st.markdown("**Interventions enregistrées aujourd'hui (ouvertes et clôturées)**")
    today = intervention_day_df()
    if today.empty:
        st.info("Aucune arrivée déclarée aujourd'hui.")
    else:
        today = format_dates(today, ["arrival_at", "departure_at"])
        st.dataframe(today, hide_index=True, use_container_width=True, height=300)


def arrival_tab(sites: pd.DataFrame, teams: pd.DataFrame):
    st.subheader("📍 Arrivée du technicien sur site")
    st.caption("La validation enregistre automatiquement la date et l'heure de présence.")
    techs = technicians_df()
    if sites.empty or techs.empty:
        st.error("Renseignez d'abord les sites et au moins un technicien actif dans l'annuaire.")
        arrival_kpi_and_table()
        return
    site_names = {int(r.site_id): f"{r.code_site} — {r.site_name}" for r in sites.itertuples()}
    team_names = {int(r.team_id): str(r.team_name) for r in teams.itertuples()}
    tech_names = {
        int(r.technician_id): f"{r.full_name} — {r.contact_number}"
        for r in techs.itertuples()
    }
    with st.form("arrival_intervention_v2", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            site_id = st.selectbox("Code site *", list(site_names), format_func=lambda x: site_names[x])
            tech_id = st.selectbox("Technicien / Team leader (nom et contact) *",
                                   list(tech_names), format_func=lambda x: tech_names[x])
        with c2:
            team_id = st.selectbox("Nom de l'équipe", [None] + list(team_names),
                                   format_func=lambda x: "— Non affectée —" if x is None else team_names[x])
            nature = selectable_lookup("Nature de l'intervention *", "INTERVENTION_TYPE", required=True)
        arrival_comment = st.text_area("Commentaire d'arrivée / motif")
        submitted = st.form_submit_button("✅ Valider — équipe SUR SITE", type="primary")
    if submitted:
        if not nature:
            st.error("Ajoutez d'abord une nature d'intervention dans Administration.")
        else:
            try:
                new_id = begin_visit(int(site_id), None if team_id is None else int(team_id),
                                     int(tech_id), nature, arrival_comment)
                flash(f"Arrivée enregistrée (intervention #{new_id}) : équipe SUR SITE.")
            except Exception as exc:
                st.error(f"Arrivée non enregistrée : {exc}")

    arrival_kpi_and_table()


def select_active_intervention(active: pd.DataFrame, key: str, label: str):
    if active.empty:
        st.info("Aucune intervention active disponible.")
        return None
    ids = active["intervention_id"].astype(int).tolist()
    labels = {
        int(r.intervention_id): f"#{int(r.intervention_id)} — {r.code_site} | {r.team_name} | {r.technician_name}"
        for r in active.itertuples()
    }
    return st.selectbox(label, ids, format_func=lambda x: labels[x], key=key)


def technical_tab(active: pd.DataFrame):
    st.subheader("🛠️ Fiche technique de l'intervention")
    st.caption("Les choix proviennent de Supabase ; 0 signifie aucun équipement, vide signifie non vérifié.")
    visit_id = select_active_intervention(active, "technical_visit_v2", "Sélectionner l'intervention")
    if visit_id is None:
        return
    info = active.loc[active["intervention_id"] == visit_id].iloc[0]
    defaults = latest_report(int(visit_id), int(info["site_id"]))
    st.info("Fiche préremplie avec le dernier relevé de ce site : vérifiez avant de sauvegarder.")
    with st.form(f"technical_report_v2_{visit_id}"):
        state = selectable_lookup("État du site", "SITE_STATE",
                                  default=text_default(defaults, "site_state") or "NON_VERIFIE", required=True)
        st.markdown("#### PowerCore et redresseurs")
        a, b = st.columns(2)
        with a:
            powercore_type = selectable_lookup("Type PowerCore", "POWERCORE_TYPE",
                                               text_default(defaults, "powercore_type") or None)
            rectifiers = st.number_input("Nombre de redresseurs installés", min_value=0, step=1,
                                          value=num_default(defaults, "rectifier_count"),
                                          placeholder="Non vérifié")
            rectifiers_bad = st.number_input("Redresseurs hors production", min_value=0, step=1,
                                              value=num_default(defaults, "rectifier_out_of_service"),
                                              placeholder="Non vérifié")
        with b:
            powercore_model = selectable_lookup("Modèle PowerCore", "POWERCORE_MODEL",
                                                text_default(defaults, "powercore_model") or None)
            chargers = st.number_input("Nombre de chargeurs solaires installés", min_value=0, step=1,
                                        value=num_default(defaults, "solar_charger_count"),
                                        placeholder="Non vérifié")
            chargers_bad = st.number_input("Chargeurs solaires hors production", min_value=0, step=1,
                                            value=num_default(defaults, "solar_charger_out_of_service"),
                                            placeholder="Non vérifié")
        pc_comment = st.text_area("Remarque PowerCore", value=text_default(defaults, "powercore_comment"))

        st.markdown("#### Groupe électrogène")
        a, b, c = st.columns(3)
        with a:
            ge_type = selectable_lookup("Type de GE", "GENSET_TYPE", text_default(defaults, "genset_type") or None)
        with b:
            ge_model = selectable_lookup("Modèle GE", "GENSET_MODEL", text_default(defaults, "genset_model") or None)
        with c:
            ge_kva = st.number_input("Genset Power (kVA)", min_value=0.0, step=0.5, format="%.1f",
                                      value=float_default(defaults, "genset_power_kva"),
                                      placeholder="Non vérifié")
        ge_comment = st.text_area("Remarque GE", value=text_default(defaults, "genset_comment"))

        st.markdown("#### Batteries")
        a, b, c = st.columns(3)
        with a:
            battery_type = selectable_lookup("Battery Type", "BATTERY_TYPE",
                                             text_default(defaults, "battery_type") or None)
        with b:
            battery_chemistry = selectable_lookup("Lithium / ACID", "BATTERY_CHEMISTRY",
                                                  text_default(defaults, "battery_chemistry") or None)
        with c:
            battery_count = st.number_input("Nombre d'éléments batteries", min_value=0, step=1,
                                             value=num_default(defaults, "battery_element_count"),
                                             placeholder="Non vérifié")
        battery_comment = st.text_area("Remarque batteries", value=text_default(defaults, "battery_comment"))

        st.markdown("#### Installation solaire")
        a, b = st.columns(2)
        with a:
            pv_type = selectable_lookup("Type de panneaux solaires (PVs)", "PV_TYPE",
                                        text_default(defaults, "pv_panel_type") or None)
        with b:
            panel_count = st.number_input("Nombre de panneaux PV", min_value=0, step=1,
                                          value=num_default(defaults, "pv_panel_count"),
                                          placeholder="Non vérifié")
        solar_comment = st.text_area("Remarque installation solaire",
                                      value=text_default(defaults, "solar_comment"))

        st.markdown("##### Potentiel d'extension solaire")
        extension_choices = ["NON_VERIFIE", "OUI", "NON"]
        extension_default = text_default(defaults, "solar_extension_possible").strip().upper()
        if extension_default not in extension_choices:
            extension_default = "NON_VERIFIE"
        extension_possible = st.selectbox(
            "Y a-t-il d’espace disponible pour une extension de l’installation solaire ?",
            extension_choices,
            index=extension_choices.index(extension_default),
            format_func=lambda value: {
                "NON_VERIFIE": "Non vérifié", "OUI": "Oui", "NON": "Non",
            }[value],
            help="Indiquez si la surface disponible permet une extension photovoltaïque.",
        )
        extension_comment = st.text_area(
            "Commentaire sur la possibilité d'extension solaire",
            value=text_default(defaults, "solar_extension_comment"),
            placeholder="Ex. : Toit disponible pour 12 PV supplémentaires ; vérifier structure, ombrage et orientation.",
        )
        submit = st.form_submit_button("💾 Enregistrer le relevé technique", type="primary")

    if submit:
        if ((rectifiers_bad is not None and rectifiers is not None and rectifiers_bad > rectifiers)
            or (chargers_bad is not None and chargers is not None and chargers_bad > chargers)):
            st.error("La quantité hors production ne peut pas être supérieure à la quantité installée.")
            return
        report = {
            "site_state": state or "NON_VERIFIE",
            "powercore_type": powercore_type,
            "powercore_model": powercore_model,
            "rectifier_count": rectifiers,
            "rectifier_out_of_service": rectifiers_bad,
            "solar_charger_count": chargers,
            "solar_charger_out_of_service": chargers_bad,
            "powercore_comment": safe_text(pc_comment),
            "genset_type": ge_type,
            "genset_model": ge_model,
            "genset_power_kva": ge_kva,
            "genset_comment": safe_text(ge_comment),
            "battery_type": battery_type,
            "battery_chemistry": battery_chemistry,
            "battery_element_count": battery_count,
            "battery_comment": safe_text(battery_comment),
            "pv_panel_type": pv_type,
            "pv_panel_count": panel_count,
            "solar_comment": safe_text(solar_comment),
            "solar_extension_possible": extension_possible,
            "solar_extension_comment": safe_text(extension_comment),
        }
        try:
            save_technical_report(int(visit_id), report)
            flash(f"Fiche technique enregistrée pour l'intervention #{visit_id}.")
        except Exception as exc:
            st.error(f"Impossible de sauvegarder : {exc}")


def departure_tab(active: pd.DataFrame):
    st.subheader("🚪 Départ / clôture d'intervention")
    visit_id = select_active_intervention(active, "departure_visit_v2", "Intervention à clôturer")
    if visit_id is None:
        return
    with st.form(f"departure_form_v2_{visit_id}"):
        comment = st.text_area("Commentaire de départ / travaux réalisés *")
        submit = st.form_submit_button("✅ Confirmer le départ", type="primary")
    if submit:
        if not comment.strip():
            st.error("Commentaire de départ obligatoire.")
        else:
            try:
                end_visit(int(visit_id), comment)
                flash(f"Départ confirmé et intervention #{visit_id} clôturée.")
            except Exception as exc:
                st.error(f"Impossible d'enregistrer le départ : {exc}")


def monitor_df():
    return read_sql("SELECT * FROM public.v_site_intervention_monitor ORDER BY active_interventions DESC, code_site")


@st.fragment(run_every="20s")
def live_monitor():
    st.subheader("📡 Supervision des sites et équipements")
    st.caption("Actualisation automatique : 20 secondes pendant que la session est ouverte")
    df = monitor_df()
    if df.empty:
        st.info("Aucun site trouvé.")
        return
    presence = df["presence_status"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sites suivis", int(len(df)))
    c2.metric("Sites avec équipe", int(presence.get("SUR_SITE", 0)))
    c3.metric("Interventions en cours", int(df["active_interventions"].sum()))
    c4.metric("Sites avec fiche technique", int(df["last_technical_report_at"].notna().sum()))
    a, b = st.columns(2)
    with a:
        status = st.selectbox("Présence", ["TOUS", "SUR_SITE", "A_QUITTE_SITE", "AUCUNE_INTERVENTION"],
                              key="monitor_presence_v2")
    with b:
        search = st.text_input("Rechercher site / équipe / technicien", key="monitor_search_v2")
    if status != "TOUS":
        df = df[df["presence_status"] == status].copy()
    if search.strip():
        match = (
            df["code_site"].fillna("").astype(str).str.contains(search, case=False, regex=False) |
            df["teams_on_site"].fillna("").astype(str).str.contains(search, case=False, regex=False) |
            df["technicians_on_site"].fillna("").astype(str).str.contains(search, case=False, regex=False)
        )
        df = df[match].copy()
    cols = [
        "code_site", "site_name", "presence_status", "active_interventions",
        "teams_on_site", "technicians_on_site", "first_arrival_at",
        "last_departure_at", "last_departure_comment", "site_state",
        "powercore_type", "powercore_model", "rectifier_count", "rectifier_out_of_service",
        "solar_charger_count", "solar_charger_out_of_service", "powercore_comment",
        "genset_type", "genset_model", "genset_power_kva", "genset_comment",
        "battery_type", "battery_chemistry", "battery_element_count", "battery_comment",
        "pv_panel_type", "pv_panel_count", "solar_comment",
        "solar_extension_possible", "solar_extension_comment", "last_technical_update_at",
        "last_reporting_technician", "last_reporting_contact",
    ]
    cols = [c for c in cols if c in df.columns]
    shown = format_dates(df[cols], ["first_arrival_at", "last_departure_at", "last_technical_update_at"])
    st.dataframe(shown, hide_index=True, use_container_width=True, height=610,
                 column_config={
                     "code_site": st.column_config.TextColumn("Code site", pinned=True),
                     "presence_status": st.column_config.TextColumn("Présence terrain", pinned=True),
                     "site_state": "État du site",
                     "genset_power_kva": "GE kVA",
                     "battery_element_count": "Nombre éléments batteries",
                     "pv_panel_type": "Type PV",
                     "pv_panel_count": "Nombre PV",
                     "solar_extension_possible": "Extension solaire ?",
                     "solar_extension_comment": "Commentaire extension",
                 })
    # Export des données EXACTEMENT filtrées et affichées ci-dessus.
    # Chaque onglet Excel conserve le même périmètre de codes sites.
    try:
        visible_codes = set(df["code_site"].dropna().astype(str))
        active_export = list_active_interventions()
        active_export = active_export[
            active_export["code_site"].astype(str).isin(visible_codes)
        ].copy()
        history_export = load_intervention_history()
        history_export = history_export[
            history_export["code_site"].astype(str).isin(visible_codes)
        ].copy()
        description = f"Présence : {status} · Recherche : {search.strip() or 'aucune'}"
        excel_bytes = export_interventions_xlsx(df[cols], active_export, history_export, description)
        st.download_button(
            "📥 Exporter l'état des sites (Excel formaté)",
            data=excel_bytes,
            file_name=f"Etat_sites_interventions_{datetime.now(ZoneInfo(TIMEZONE)):%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="export_tech_sites_excel_v3",
        )
        st.caption("4 feuilles : Synthèse · État des sites · Équipes sur site · Historique (2 000 dernières interventions max).")
    except ImportError:
        st.error("Ajoutez 'XlsxWriter' à votre requirements.txt pour activer l'export Excel.")
    except Exception as exc:
        st.error(f"Export Excel indisponible : {exc}")


def history_tab():
    st.subheader("📚 Historique des interventions")
    df = load_intervention_history()
    if df.empty:
        st.info("Pas encore d'historique.")
        return
    shown = format_dates(df, ["arrival_at", "departure_at", "report_updated_at"])
    st.dataframe(shown, hide_index=True, use_container_width=True, height=550)
    st.download_button("⬇️ Exporter historique CSV", shown.to_csv(index=False).encode("utf-8-sig"),
                       file_name="historique_interventions.csv", mime="text/csv")


def admin_authorized() -> bool:
    """Code admin obligatoire : ne jamais committer le PIN dans GitHub."""
    try:
        stored_pin = str(st.secrets.get("INTERVENTION_ADMIN_PIN", "")).strip()
    except Exception:
        stored_pin = ""
    if not stored_pin:
        st.warning("Administration désactivée : ajoutez INTERVENTION_ADMIN_PIN dans Streamlit Secrets.")
        return False
    entered = st.text_input("Code administrateur", type="password", key="admin_pin_interventions")
    if not entered:
        return False
    if not hmac.compare_digest(entered, stored_pin):
        st.error("Code incorrect.")
        return False
    return True


def administration_tab(teams: pd.DataFrame):
    st.subheader("⚙️ Administration des listes de choix et des techniciens")
    st.caption("Les valeurs sont conservées dans Supabase, puis proposées dans tous les formulaires.")
    if not admin_authorized():
        return

    st.markdown("#### Ajouter une option dans une liste")
    with st.form("new_dropdown_value_v2", clear_on_submit=True):
        category = st.selectbox("Famille de choix", list(CATEGORIES.keys()),
                                format_func=lambda x: CATEGORIES[x])
        value = st.text_input("Nouvelle valeur", max_chars=255,
                              placeholder="Ex. FG WILSON, JASolar 590W, FP2...")
        submit = st.form_submit_button("➕ Ajouter l'option")
    if submit:
        if not value.strip():
            st.error("La valeur est obligatoire.")
        else:
            try:
                execute_sql("""
                    INSERT INTO public.intervention_lookup_options(category, option_value)
                    VALUES (:category, :value)
                    ON CONFLICT (category, option_value)
                    DO UPDATE SET is_active=TRUE, updated_at=NOW()
                """, {"category": category, "value": value.strip()})
                flash(f"Option « {value.strip()} » disponible dans {CATEGORIES[category]}.")
            except Exception as exc:
                st.error(f"Ajout impossible : {exc}")

    current_options = read_sql("""
        SELECT option_id, category, option_value, is_active
        FROM public.intervention_lookup_options
        ORDER BY category, sort_order, option_value
    """)
    with st.expander("Gérer les valeurs existantes (activer / désactiver)"):
        st.dataframe(current_options, hide_index=True, use_container_width=True, height=260)
        if not current_options.empty:
            opt_ids = current_options["option_id"].astype(int).tolist()
            opt_labels = {int(r.option_id): f"{CATEGORIES.get(r.category,r.category)} — {r.option_value}"
                          for r in current_options.itertuples()}
            option_id = st.selectbox("Choisir une option", opt_ids, format_func=lambda x: opt_labels[x])
            active = bool(current_options.loc[current_options["option_id"]==option_id, "is_active"].iloc[0])
            if st.button("Désactiver" if active else "Réactiver", key="switch_dropdown_v2"):
                execute_sql("""
                    UPDATE public.intervention_lookup_options
                    SET is_active=:active, updated_at=NOW()
                    WHERE option_id=:id
                """, {"id": option_id, "active": not active})
                flash("Liste de choix mise à jour.")

    st.divider()
    st.markdown("#### Annuaire des techniciens / Team leaders")
    with st.form("new_technician_v2", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Nom du technicien *", max_chars=150)
        with c2:
            phone = st.text_input("Numéro de contact *", max_chars=40,
                                  help="Saisi comme texte pour conserver les zéros initiaux.")
        with c3:
            team_map = {int(r.team_id): str(r.team_name) for r in teams.itertuples()}
            team_id = st.selectbox("Équipe habituelle (facultatif)", [None]+list(team_map),
                                   format_func=lambda x: "— Non affectée —" if x is None else team_map[x])
        tech_submit = st.form_submit_button("➕ Ajouter le technicien")
    if tech_submit:
        if not name.strip() or not phone.strip():
            st.error("Nom et contact obligatoires.")
        else:
            try:
                execute_sql("""
                    INSERT INTO public.intervention_technicians(full_name, contact_number, team_id)
                    VALUES (:name, :phone, :team_id)
                    ON CONFLICT (full_name, contact_number)
                    DO UPDATE SET is_active=TRUE,
                                  team_id=EXCLUDED.team_id, updated_at=NOW()
                """, {"name": name.strip(), "phone": phone.strip(), "team_id": team_id})
                flash(f"Technicien {name.strip()} disponible.")
            except Exception as exc:
                st.error(f"Ajout impossible : {exc}")

    people = technicians_df(active_only=False)
    if not people.empty:
        st.dataframe(people, hide_index=True, use_container_width=True)
        with st.expander("Modifier contact / équipe / activité d'un technicien"):
            ids = people["technician_id"].astype(int).tolist()
            labels = {int(r.technician_id): f"{r.full_name} — {r.contact_number}"
                      for r in people.itertuples()}
            tech_id = st.selectbox("Technicien", ids, format_func=lambda x: labels[x])
            tech_row = people.loc[people["technician_id"]==tech_id].iloc[0]
            with st.form(f"edit_technician_v2_{tech_id}"):
                phone_edit = st.text_input("Contact", value=str(tech_row["contact_number"]))
                active_edit = st.checkbox("Actif", value=bool(tech_row["is_active"]))
                team_map = {int(r.team_id): str(r.team_name) for r in teams.itertuples()}
                available_teams = [None] + list(team_map)
                prev_team = tech_row["team_id"]
                prev_team = None if pd.isna(prev_team) else int(prev_team)
                pos = available_teams.index(prev_team) if prev_team in available_teams else 0
                team_edit = st.selectbox("Équipe habituelle", available_teams, index=pos,
                                         format_func=lambda x: "— Non affectée —" if x is None else team_map[x])
                update = st.form_submit_button("💾 Mettre à jour")
            if update:
                if not phone_edit.strip():
                    st.error("Le contact ne peut pas être vide.")
                else:
                    try:
                        execute_sql("""
                            UPDATE public.intervention_technicians
                            SET contact_number=:phone, team_id=:team_id,
                                is_active=:active, updated_at=NOW()
                            WHERE technician_id=:id
                        """, {"phone": phone_edit.strip(), "team_id": team_edit,
                               "active": active_edit, "id": tech_id})
                        flash("Fiche technicien mise à jour.")
                    except Exception as exc:
                        st.error(f"Mise à jour impossible : {exc}")

    st.divider()
    st.markdown("#### Équipes")
    st.caption("Les équipes existantes sont lues directement depuis public.teams.")
    with st.form("add_team_v2", clear_on_submit=True):
        new_team = st.text_input("Nom de la nouvelle équipe", max_chars=150)
        submit_team = st.form_submit_button("➕ Ajouter l'équipe")
    if submit_team and new_team.strip():
        try:
            exists = read_sql("""
                SELECT 1 FROM public.teams WHERE LOWER(TRIM(team_name))=LOWER(TRIM(:name)) LIMIT 1
            """, {"name": new_team.strip()})
            if not exists.empty:
                st.warning("Équipe déjà présente.")
            else:
                execute_sql("INSERT INTO public.teams(team_name) VALUES (:name)",
                            {"name": new_team.strip()})
                flash("Nouvelle équipe ajoutée.")
        except Exception as exc:
            st.error("Ajout d'équipe impossible : vérifiez les champs obligatoires de public.teams. " + str(exc))


def show_interventions_dashboard():
    st.title("🧰 Suivi des interventions terrain")
    st.caption("Arrivées / départs · Inventaire PowerCore / GE / Batteries / PV · Listes administrables")
    if message := st.session_state.pop("interventions_flash_v2", None):
        st.success(message)
    try:
        sites = sites_df()
        teams = teams_df()
        active = list_active_interventions()
        # Vérifie aussi l'existence de la migration V2.
        lookup_values("GENSET_TYPE")
    except Exception as exc:
        st.error("Impossible de charger le module. Exécutez d'abord le SQL V1 puis la migration V2 sur Supabase.")
        st.exception(exc)
        return
    a, b, c, d, e, f = st.tabs([
        "📍 Arrivée", "🛠️ Fiche technique", "🚪 Départ", "📡 Supervision",
        "📚 Historique", "⚙️ Administration",
    ])
    with a:
        arrival_tab(sites, teams)
    with b:
        technical_tab(active)
    with c:
        departure_tab(active)
    with d:
        live_monitor()
    with e:
        history_tab()
    with f:
        administration_tab(teams)


if __name__ == "__main__":
    show_interventions_dashboard()
