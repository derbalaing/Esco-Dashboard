import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import date
from io import BytesIO

from config.database import engine


# ==================================================
# HELPERS SQL
# ==================================================

def read_sql(query, params=None):
    with engine.connect() as conn:
        return pd.read_sql(
            text(query),
            conn,
            params=params
        )


def execute_sql(query, params=None):
    with engine.begin() as conn:
        conn.execute(
            text(query),
            params or {}
        )


# ==================================================
# SECURITE : CREATION / AJOUT COLONNES
# ==================================================

def ensure_site_actions_table():
    query = """
    CREATE TABLE IF NOT EXISTS public.site_actions
    (
        action_id SERIAL PRIMARY KEY,

        site_id INTEGER NOT NULL REFERENCES public.sites(site_id) ON DELETE CASCADE,

        project_name VARCHAR(150),
        client_name VARCHAR(150),

        notification_date DATE,
        requested_action TEXT,
        action_type VARCHAR(100),
        pda_description TEXT,

        action_status VARCHAR(50) DEFAULT 'OUVERT',
        remark TEXT,

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    ALTER TABLE public.site_actions
    ADD COLUMN IF NOT EXISTS project_name VARCHAR(150),
    ADD COLUMN IF NOT EXISTS client_name VARCHAR(150),
    ADD COLUMN IF NOT EXISTS notification_date DATE,
    ADD COLUMN IF NOT EXISTS requested_action TEXT,
    ADD COLUMN IF NOT EXISTS action_type VARCHAR(100),
    ADD COLUMN IF NOT EXISTS pda_description TEXT,
    ADD COLUMN IF NOT EXISTS action_status VARCHAR(50) DEFAULT 'OUVERT',
    ADD COLUMN IF NOT EXISTS remark TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

    CREATE INDEX IF NOT EXISTS idx_site_actions_site_id
    ON public.site_actions(site_id);

    CREATE INDEX IF NOT EXISTS idx_site_actions_project_name
    ON public.site_actions(project_name);

    CREATE INDEX IF NOT EXISTS idx_site_actions_client_name
    ON public.site_actions(client_name);

    CREATE INDEX IF NOT EXISTS idx_site_actions_status
    ON public.site_actions(action_status);
    """

    execute_sql(query)


# ==================================================
# DATA
# ==================================================

@st.cache_data(ttl=300)
def load_sites():
    query = """
    SELECT
        site_id,
        code_site,
        COALESCE(site_name, '') AS site_name
    FROM public.sites
    ORDER BY code_site;
    """

    return read_sql(query)


@st.cache_data(ttl=300)
def load_actions():
    query = """
    SELECT
        source_type,
        source_id,
        site_id,
        code_site,
        site_name,
        project_name,
        client_name,
        notification_date,
        requested_action,
        action_type,
        pda_description,
        action_status,
        remark,
        created_at,
        updated_at
    FROM public.v_all_site_actions
    ORDER BY
        notification_date DESC NULLS LAST,
        created_at DESC NULLS LAST;
    """

    return read_sql(query)


def insert_action(
    site_id,
    project_name,
    client_name,
    notification_date,
    requested_action,
    action_type,
    pda_description,
    action_status,
    remark
):
    query = """
    INSERT INTO public.site_actions
    (
        site_id,
        project_name,
        client_name,
        notification_date,
        requested_action,
        action_type,
        pda_description,
        action_status,
        remark,
        updated_at
    )
    VALUES
    (
        :site_id,
        :project_name,
        :client_name,
        :notification_date,
        :requested_action,
        :action_type,
        :pda_description,
        :action_status,
        :remark,
        NOW()
    );
    """

    params = {
        "site_id": site_id,
        "project_name": project_name,
        "client_name": client_name,
        "notification_date": notification_date,
        "requested_action": requested_action,
        "action_type": action_type,
        "pda_description": pda_description,
        "action_status": action_status,
        "remark": remark,
    }

    execute_sql(query, params)


# ==================================================
# PAGE STREAMLIT
# ==================================================

def show_site_actions():

    ensure_site_actions_table()

    st.title("📌 Suivi des actions / mini-projets par site")

    st.caption(
        "Cette page permet d’ajouter et suivre les actions demandées par site : projet, client, notification, PDA, état et remarque."
    )

    sites_df = load_sites()

    if sites_df.empty:
        st.error("Aucun site trouvé dans la table sites.")
        st.stop()

    site_options = sites_df.copy()
    site_options["label"] = (
        site_options["code_site"].astype(str)
        + " - "
        + site_options["site_name"].fillna("").astype(str)
    )

    site_label_to_id = dict(
        zip(
            site_options["label"],
            site_options["site_id"]
        )
    )

    tab_form, tab_list = st.tabs(
        [
            "➕ Ajouter une action",
            "📋 Liste des actions"
        ]
    )

    # ==================================================
    # FORMULAIRE AJOUT ACTION
    # ==================================================

    with tab_form:

        st.subheader("➕ Nouvelle action")

        with st.form("form_add_site_action", clear_on_submit=True):

            c1, c2 = st.columns(2)

            with c1:
                selected_site_label = st.selectbox(
                    "Site",
                    site_options["label"].tolist()
                )

                project_name = st.text_input(
                    "Nom du projet",
                    placeholder="Exemple : Upgrade Energie 2026"
                )

                client_name = st.text_input(
                    "Nom du client",
                    placeholder="Exemple : MTN Cameroun / Orange / OCI"
                )

                notification_date = st.date_input(
                    "Date de notification",
                    value=date.today()
                )

            with c2:
                action_type = st.selectbox(
                    "Type d'action",
                    [
                        "Upgrade Energie",
                        "Ajout GE",
                        "Remplacement GE",
                        "Ajout redresseurs",
                        "Ajout chargeurs solaires",
                        "Ajout panneaux PV",
                        "Remplacement batteries",
                        "Normalisation site",
                        "Correction PWC",
                        "Audit",
                        "Autre"
                    ]
                )

                action_status = st.selectbox(
                    "État",
                    [
                        "OUVERT",
                        "EN_COURS",
                        "BLOQUE",
                        "TERMINE",
                        "ANNULE"
                    ]
                )

            requested_action = st.text_area(
                "Action demandée",
                placeholder="Décrire clairement l’action demandée..."
            )

            pda_description = st.text_area(
                "Description PDA",
                placeholder="Description PDA / justification / besoin technique..."
            )

            remark = st.text_area(
                "Remarque",
                placeholder="Remarque complémentaire..."
            )

            submitted = st.form_submit_button("💾 Enregistrer l'action")

            if submitted:

                site_id = site_label_to_id[selected_site_label]

                if not requested_action.strip():
                    st.error("L’action demandée est obligatoire.")

                else:
                    insert_action(
                        site_id=site_id,
                        project_name=project_name.strip(),
                        client_name=client_name.strip(),
                        notification_date=notification_date,
                        requested_action=requested_action.strip(),
                        action_type=action_type,
                        pda_description=pda_description.strip(),
                        action_status=action_status,
                        remark=remark.strip()
                    )

                    st.cache_data.clear()

                    st.success("✅ Action ajoutée avec succès.")

    # ==================================================
    # LISTE ACTIONS
    # ==================================================

    with tab_list:

        st.subheader("📋 Liste des actions")

        df_actions = load_actions()

        if df_actions.empty:
            st.info("Aucune action enregistrée.")
            st.stop()

        df_actions["notification_date"] = pd.to_datetime(
            df_actions["notification_date"],
            errors="coerce"
        ).dt.date

        # -----------------------------
        # Filtres
        # -----------------------------

        f1, f2, f3, f4 = st.columns(4)

        with f1:
            project_filter = st.selectbox(
                "Projet",
                ["TOUS"] + sorted(
                    df_actions["project_name"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                )
            )

        with f2:
            client_filter = st.selectbox(
                "Client",
                ["TOUS"] + sorted(
                    df_actions["client_name"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                )
            )

        with f3:
            status_filter = st.selectbox(
                "État",
                ["TOUS"] + sorted(
                    df_actions["action_status"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                )
            )

        with f4:
            type_filter = st.selectbox(
                "Type d'action",
                ["TOUS"] + sorted(
                    df_actions["action_type"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                )
            )

        df_filtered = df_actions.copy()

        if project_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["project_name"].fillna("Non défini").astype(str) == project_filter
            ]

        if client_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["client_name"].fillna("Non défini").astype(str) == client_filter
            ]

        if status_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["action_status"].fillna("Non défini").astype(str) == status_filter
            ]

        if type_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["action_type"].fillna("Non défini").astype(str) == type_filter
            ]

        # -----------------------------
        # KPI
        # -----------------------------

        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.metric(
                "Total actions",
                len(df_filtered)
            )

        with k2:
            st.metric(
                "Ouvertes",
                len(df_filtered[df_filtered["action_status"] == "OUVERT"])
            )

        with k3:
            st.metric(
                "En cours",
                len(df_filtered[df_filtered["action_status"] == "EN_COURS"])
            )

        with k4:
            st.metric(
                "Terminées",
                len(df_filtered[df_filtered["action_status"] == "TERMINE"])
            )

        # -----------------------------
        # Tableau
        # -----------------------------

        display_cols = [
            "code_site",
            "site_name",
            "project_name",
            "client_name",
            "notification_date",
            "requested_action",
            "action_type",
            "pda_description",
            "action_status",
            "remark"
        ]

        st.dataframe(
            df_filtered[display_cols],
            use_container_width=True,
            hide_index=True,
            height=550
        )

        # -----------------------------
        # Export CSV
        # -----------------------------

        csv = df_filtered[display_cols].to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            label="⬇️ Télécharger CSV",
            data=csv,
            file_name="site_actions.csv",
            mime="text/csv"
        )


def show_site_actions_list_only():

        ensure_site_actions_table()

        st.subheader("📋 Suivi des actions / mini-projets par site")

        df_actions = load_actions()

        if df_actions.empty:
            st.info("Aucune action enregistrée.")
            return

        df_actions["notification_date"] = pd.to_datetime(
            df_actions["notification_date"],
            errors="coerce"
        ).dt.date

        # ===============================
        # Filtres rapides
        # ===============================

        f1, f2, f3, f4 = st.columns(4)

        with f1:
            project_filter = st.selectbox(
                "Projet",
                ["TOUS"] + sorted(
                    df_actions["project_name"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                ),
                key="home_project_filter"
            )

        with f2:
            client_filter = st.selectbox(
                "Client",
                ["TOUS"] + sorted(
                    df_actions["client_name"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                ),
                key="home_client_filter"
            )

        with f3:
            status_filter = st.selectbox(
                "État",
                ["TOUS"] + sorted(
                    df_actions["action_status"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                ),
                key="home_status_filter"
            )

        with f4:
            type_filter = st.selectbox(
                "Type d'action",
                ["TOUS"] + sorted(
                    df_actions["action_type"]
                    .fillna("Non défini")
                    .astype(str)
                    .unique()
                    .tolist()
                ),
                key="home_type_filter"
            )

        df_filtered = df_actions.copy()

        if project_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["project_name"].fillna("Non défini").astype(str) == project_filter
            ]

        if client_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["client_name"].fillna("Non défini").astype(str) == client_filter
            ]

        if status_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["action_status"].fillna("Non défini").astype(str) == status_filter
            ]

        if type_filter != "TOUS":
            df_filtered = df_filtered[
                df_filtered["action_type"].fillna("Non défini").astype(str) == type_filter
            ]

        # ===============================
        # KPI rapides
        # ===============================

        k1, k2, k3, k4 = st.columns(4)

        with k1:
            st.metric("Total actions", len(df_filtered))

        with k2:
            st.metric(
                "Ouvertes",
                len(df_filtered[df_filtered["action_status"] == "OUVERT"])
            )

        with k3:
            st.metric(
                "En cours",
                len(df_filtered[df_filtered["action_status"] == "EN_COURS"])
            )

        with k4:
            st.metric(
                "Terminées",
                len(df_filtered[df_filtered["action_status"] == "TERMINE"])
            )


        # ===============================
        # Tableau élégant
        # ===============================

        display_cols = [
            "code_site",
            "site_name",
            "project_name",
            "client_name",
            "notification_date",
            "requested_action",
            "action_type",
            "pda_description",
            "action_status",
            "remark"
        ]

        display_cols = [
            col for col in display_cols
            if col in df_filtered.columns
        ]

        df_table = df_filtered[display_cols].copy()

        # Renommer les colonnes pour l'affichage
        df_table = df_table.rename(
            columns={
                "source_type": "Source",
                "code_site": "Code site",
                "site_name": "Nom site",
                "project_name": "Projet",
                "client_name": "Client",
                "notification_date": "Date notification",
                "requested_action": "Action demandée",
                "action_type": "Type d'action",
                "pda_description": "Description PDA",
                "action_status": "État",
                "remark": "Remarque"
            }
        )

        # Nettoyage dates
        if "Date notification" in df_table.columns:
            df_table["Date notification"] = pd.to_datetime(
                df_table["Date notification"],
                errors="coerce"
            ).dt.strftime("%d/%m/%Y")


        def style_action_rows(row):
            status = str(row.get("État", "")).strip().upper()

            if status == "OUVERT":
                return [
                    "background-color: #fff7ed; color: #9a3412; font-weight: 600"
                    if col == "État" else ""
                    for col in row.index
                ]

            if status == "EN_COURS":
                return [
                    "background-color: #eff6ff; color: #1d4ed8; font-weight: 600"
                    if col == "État" else ""
                    for col in row.index
                ]

            if status == "TERMINE":
                return [
                    "background-color: #ecfdf5; color: #047857; font-weight: 600"
                    if col == "État" else ""
                    for col in row.index
                ]

            if status == "BLOQUE":
                return [
                    "background-color: #fef2f2; color: #b91c1c; font-weight: 700"
                    if col == "État" else ""
                    for col in row.index
                ]

            if status == "ANNULE":
                return [
                    "background-color: #f3f4f6; color: #374151; font-weight: 600"
                    if col == "État" else ""
                    for col in row.index
                ]

            return ["" for _ in row.index]


        styled_table = (
            df_table
            .style
            .apply(style_action_rows, axis=1)
            .set_properties(
                **{
                    "font-size": "13px",
                    "border-color": "#e5e7eb"
                }
            )
        )

        st.markdown(
            """
            <style>
            div[data-testid="stDataFrame"] {
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid #e5e7eb;
                box-shadow: 0 4px 14px rgba(0,0,0,0.08);
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        st.dataframe(
            styled_table,
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "Code site": st.column_config.TextColumn(
                    "Code site",
                    width="small"
                ),
                "Nom site": st.column_config.TextColumn(
                    "Nom site",
                    width="medium"
                ),
                "Projet": st.column_config.TextColumn(
                    "Projet",
                    width="medium"
                ),
                "Client": st.column_config.TextColumn(
                    "Client",
                    width="medium"
                ),
                "Date notification": st.column_config.TextColumn(
                    "Date notification",
                    width="small"
                ),
                "Action demandée": st.column_config.TextColumn(
                    "Action demandée",
                    width="large"
                ),
                "Type d'action": st.column_config.TextColumn(
                    "Type d'action",
                    width="medium"
                ),
                "Description PDA": st.column_config.TextColumn(
                    "Description PDA",
                    width="large"
                ),
                "État": st.column_config.TextColumn(
                    "État",
                    width="small"
                ),
                "Remarque": st.column_config.TextColumn(
                    "Remarque",
                    width="large"
                ),
            }
        )

        excel_file = export_actions_excel(df_table)

        st.download_button(
            label="⬇️ Exporter Excel avec mise en forme",
            data=excel_file,
            file_name="suivi_actions_sites.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def export_actions_excel(df_table):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        sheet_name = "Suivi Actions"
        df_table.to_excel(
            writer,
            index=False,
            sheet_name=sheet_name,
            startrow=1
        )

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # ===============================
        # Formats
        # ===============================

        title_format = workbook.add_format({
            "bold": True,
            "font_size": 16,
            "font_color": "white",
            "bg_color": "#1f2937",
            "align": "center",
            "valign": "vcenter"
        })

        header_format = workbook.add_format({
            "bold": True,
            "font_color": "white",
            "bg_color": "#374151",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True
        })

        normal_format = workbook.add_format({
            "border": 1,
            "valign": "top",
            "text_wrap": True
        })

        date_format = workbook.add_format({
            "border": 1,
            "num_format": "dd/mm/yyyy",
            "align": "center",
            "valign": "top"
        })

        ouvert_format = workbook.add_format({
            "bg_color": "#fff7ed",
            "font_color": "#9a3412",
            "bold": True,
            "border": 1,
            "align": "center"
        })

        encours_format = workbook.add_format({
            "bg_color": "#eff6ff",
            "font_color": "#1d4ed8",
            "bold": True,
            "border": 1,
            "align": "center"
        })

        termine_format = workbook.add_format({
            "bg_color": "#ecfdf5",
            "font_color": "#047857",
            "bold": True,
            "border": 1,
            "align": "center"
        })

        bloque_format = workbook.add_format({
            "bg_color": "#fef2f2",
            "font_color": "#b91c1c",
            "bold": True,
            "border": 1,
            "align": "center"
        })

        annule_format = workbook.add_format({
            "bg_color": "#f3f4f6",
            "font_color": "#374151",
            "bold": True,
            "border": 1,
            "align": "center"
        })

        # ===============================
        # Titre
        # ===============================

        last_col = len(df_table.columns) - 1

        worksheet.merge_range(
            0,
            0,
            0,
            last_col,
            "Suivi des actions / mini-projets par site",
            title_format
        )

        worksheet.set_row(0, 28)

        # ===============================
        # Header
        # ===============================

        for col_num, col_name in enumerate(df_table.columns):
            worksheet.write(
                1,
                col_num,
                col_name,
                header_format
            )

        worksheet.freeze_panes(2, 1)
        worksheet.autofilter(1, 0, len(df_table) + 1, last_col)

        # ===============================
        # Largeurs colonnes
        # ===============================

        widths = {
            "Source": 16,
            "Code site": 16,
            "Nom site": 26,
            "Projet": 28,
            "Client": 14,
            "Date notification": 18,
            "Action demandée": 42,
            "Type d'action": 24,
            "Description PDA": 45,
            "État": 15,
            "Remarque": 40
        }

        for col_num, col_name in enumerate(df_table.columns):
            worksheet.set_column(
                col_num,
                col_num,
                widths.get(col_name, 22),
                normal_format
            )

        # ===============================
        # Mise en forme par état
        # ===============================

        if "État" in df_table.columns:
            status_col = df_table.columns.get_loc("État")

            for row_num, status in enumerate(df_table["État"], start=2):

                status_clean = str(status).strip().upper()

                if status_clean == "OUVERT":
                    fmt = ouvert_format
                elif status_clean == "EN_COURS":
                    fmt = encours_format
                elif status_clean == "TERMINE":
                    fmt = termine_format
                elif status_clean == "BLOQUE":
                    fmt = bloque_format
                elif status_clean == "ANNULE":
                    fmt = annule_format
                else:
                    fmt = normal_format

                worksheet.write(
                    row_num,
                    status_col,
                    status,
                    fmt
                )

        # ===============================
        # Format date
        # ===============================

        if "Date notification" in df_table.columns:
            date_col = df_table.columns.get_loc("Date notification")

            for row_num, value in enumerate(df_table["Date notification"], start=2):
                worksheet.write(
                    row_num,
                    date_col,
                    value,
                    date_format
                )

    output.seek(0)
    return output