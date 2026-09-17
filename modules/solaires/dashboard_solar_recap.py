import streamlit as st
import pandas as pd
import base64
from sqlalchemy import text
import streamlit.components.v1 as components

from config.database import engine



# ==================================================
# SQL HELPER
# ==================================================

def read_sql(query, params=None):
    with engine.connect() as conn:
        return pd.read_sql(
            text(query),
            conn,
            params=params or {}
        )


def execute_sql(query, params=None):
    with engine.begin() as conn:
        result = conn.execute(
            text(query),
            params or {}
        )
        return result


# ==================================================
# LOAD DATA
# ==================================================

@st.cache_data(ttl=300)
def load_recap_dates():

    query = """
    SELECT
        recap_date
    FROM solar_recap_headers
    ORDER BY recap_date DESC
    """

    return read_sql(query)


@st.cache_data(ttl=300)
def load_recap_by_date(recap_date):

    query_header = """
    SELECT
        recap_id,
        recap_date,
        recap_title,
        recap_summary,
        recap_html
    FROM solar_recap_headers
    WHERE recap_date = :recap_date
    """

    df_header = read_sql(
        query_header,
        params={
            "recap_date": recap_date
        }
    )

    if df_header.empty:
        return df_header, pd.DataFrame()

    recap_id = int(df_header.iloc[0]["recap_id"])

    query_items = """
    SELECT
        item_id,
        order_index,
        image_name,
        image_mime,
        image_base64,
        title,
        kpi_name,
        kpi_value,
        unit,
        status,
        comment
    FROM solar_recap_items
    WHERE recap_id = :recap_id
    ORDER BY
        order_index,
        item_id
    """

    df_items = read_sql(
        query_items,
        params={
            "recap_id": recap_id
        }
    )

    return df_header, df_items


# ==================================================
# SAVE DATA
# ==================================================

def upsert_recap_header(recap_date, recap_title , recap_summary, recap_html=None):

    query = """
    INSERT INTO solar_recap_headers
    (
        recap_date,
        recap_title,
        recap_summary,
        recap_html,
        updated_at
    )
    VALUES
    (
        :recap_date,
        :recap_title,
        :recap_summary,
        :recap_html,
        NOW()
    )
    ON CONFLICT (recap_date)
    DO UPDATE SET
        recap_title = EXCLUDED.recap_title,
        recap_summary = EXCLUDED.recap_summary,
        recap_html = EXCLUDED.recap_html,
        updated_at = NOW()
    RETURNING recap_id
    """

    with engine.begin() as conn:
        result = conn.execute(
            text(query),
            {
                "recap_date": recap_date,
                "recap_title": recap_title,
                "recap_summary": recap_summary,
                "recap_html": recap_html,
            }
        )

        recap_id = result.scalar()

    return recap_id


def insert_recap_item(
    recap_id,
    order_index,
    image_name,
    image_mime,
    image_base64,
    title,
    kpi_name,
    kpi_value,
    unit,
    status,
    comment
):

    query = """
    INSERT INTO solar_recap_items
    (
        recap_id,
        order_index,
        image_name,
        image_mime,
        image_base64,
        title,
        kpi_name,
        kpi_value,
        unit,
        status,
        comment,
        updated_at
    )
    VALUES
    (
        :recap_id,
        :order_index,
        :image_name,
        :image_mime,
        :image_base64,
        :title,
        :kpi_name,
        :kpi_value,
        :unit,
        :status,
        :comment,
        NOW()
    )
    """

    execute_sql(
        query,
        params={
            "recap_id": recap_id,
            "order_index": order_index,
            "image_name": image_name,
            "image_mime": image_mime,
            "image_base64": image_base64,
            "title": title,
            "kpi_name": kpi_name,
            "kpi_value": kpi_value,
            "unit": unit,
            "status": status,
            "comment": comment,
        }
    )


def delete_recap_item(item_id):

    query = """
    DELETE FROM solar_recap_items
    WHERE item_id = :item_id
    """

    execute_sql(
        query,
        params={
            "item_id": int(item_id)
        }
    )


# ==================================================
# IMAGE HELPER
# ==================================================

def file_to_base64(uploaded_file):

    if uploaded_file is None:
        return None, None, None

    file_bytes = uploaded_file.read()

    image_base64 = base64.b64encode(
        file_bytes
    ).decode("utf-8")

    return uploaded_file.name, uploaded_file.type, image_base64


def image_html(image_mime, image_base64):

    if image_base64 is None or str(image_base64).strip() == "":
        return ""

    return f"""
    <img src="data:{image_mime};base64,{image_base64}"
         style="width:90px;height:70px;object-fit:cover;border-radius:10px;">
    """


# ==================================================
# PAGE
# ==================================================

def show_solar_recap():

    st.title("📝 Récap solaire journalier")

    st.caption(
        "Page de récap enregistrée par date avec images, KPI, commentaires et statuts."
    )

    if st.button("🔄 Actualiser", key="refresh_solar_recap"):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # ==================================================
    # SELECTION DATE
    # ==================================================

    df_dates = load_recap_dates()

    if df_dates.empty:

        st.info("Aucun récap enregistré pour le moment.")

        selected_recap_date = st.date_input(
            "Date du récap",
            key="solar_recap_empty_date"
        )

    else:

        df_dates["recap_date"] = pd.to_datetime(
            df_dates["recap_date"],
            errors="coerce"
        ).dt.date

        recap_dates = df_dates["recap_date"].dropna().tolist()

        selected_recap_date = st.selectbox(
            "Choisir la date du récap",
            recap_dates,
            index=0,
            key="solar_recap_date_filter"
        )

    # ==================================================
    # CHARGER RECAP
    # ==================================================

    df_header, df_items = load_recap_by_date(selected_recap_date)

    if not df_header.empty:

        header = df_header.iloc[0]

        st.subheader(
            header["recap_title"]
            if pd.notna(header["recap_title"])
            else f"Récap du {selected_recap_date}"
        )

        if pd.notna(header["recap_summary"]):
            st.info(header["recap_summary"])

    else:

        st.warning("Aucun récap trouvé pour cette date.")


    if "recap_html" in header.index and pd.notna(header["recap_html"]):

        if "recap_html" in header.index and pd.notna(header["recap_html"]):

            recap_html = str(header["recap_html"]).strip()

            if recap_html != "":
                components.html(
                    recap_html,
                    height=900,
                    scrolling=True
                )



    # ==================================================
    # AFFICHAGE TABLEAU AVEC IMAGES
    # ==================================================

    if not df_items.empty:

        rows_html = ""

        for _, row in df_items.iterrows():

            img = image_html(
                row.get("image_mime"),
                row.get("image_base64")
            )

            status = str(row.get("status", "-")).strip().upper()

            if status == "CRITICAL":
                bg_color = "#fecaca"
            elif status == "WARNING":
                bg_color = "#fef3c7"
            elif status == "OK":
                bg_color = "#dcfce7"
            else:
                bg_color = "#f8fafc"

            rows_html += f"""
            <tr style="background-color:{bg_color};">
                <td>{img}</td>
                <td><b>{row.get("title", "-")}</b></td>
                <td>{row.get("kpi_name", "-")}</td>
                <td><b>{row.get("kpi_value", "-")}</b> {row.get("unit", "")}</td>
                <td>{row.get("status", "-")}</td>
                <td>{row.get("comment", "-")}</td>
            </tr>
            """

        table_html = f"""
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background-color:#0f172a;color:white;">
                    <th style="padding:10px;">Image</th>
                    <th style="padding:10px;">Titre</th>
                    <th style="padding:10px;">Indicateur</th>
                    <th style="padding:10px;">Valeur</th>
                    <th style="padding:10px;">Statut</th>
                    <th style="padding:10px;">Commentaire</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        """

        st.markdown(
            table_html,
            unsafe_allow_html=True
        )

        st.divider()

        with st.expander("🗑️ Supprimer une ligne du récap"):

            item_options = {
                f"{row['item_id']} - {row['title']}": row["item_id"]
                for _, row in df_items.iterrows()
            }

            selected_item_label = st.selectbox(
                "Ligne à supprimer",
                list(item_options.keys()),
                key="delete_recap_item_select"
            )

            if st.button("Supprimer la ligne", key="delete_recap_item_button"):
                delete_recap_item(
                    item_options[selected_item_label]
                )
                st.cache_data.clear()
                st.rerun()

    else:

        st.info("Aucune ligne ajoutée pour ce récap.")

    st.divider()

    # ==================================================
    # FORMULAIRE CREATION / MISE A JOUR RECAP
    # ==================================================

    with st.expander("➕ Créer ou modifier un récap"):

        with st.form("form_solar_recap_header"):

            recap_date = st.date_input(
                "Date du récap",
                value=selected_recap_date,
                key="form_recap_date"
            )

            recap_title = st.text_input(
                "Titre du récap",
                value=f"Récap solaire du {selected_recap_date}",
                key="form_recap_title"
            )

            recap_summary = st.text_area(
                "Résumé général",
                placeholder="Exemple : Production globale correcte, quelques sites en LOSTCOM et plusieurs sites dégradés à suivre.",
                key="form_recap_summary"
            )

            recap_html = st.text_area(
                "Contenu HTML du récap",
                placeholder="""
            <h3>Résumé solaire</h3>

            <table style="width:100%;border-collapse:collapse;">
                <tr style="background:#0f172a;color:white;">
                    <th>Indicateur</th>
                    <th>Valeur</th>
                    <th>Commentaire</th>
                </tr>
                <tr>
                    <td>Production totale</td>
                    <td>12 500 kWh</td>
                    <td>Bonne performance globale</td>
                </tr>
            </table>
            """,
                height=350,
                key="form_recap_html"
            )

            submit_header = st.form_submit_button(
                "✅ Enregistrer le récap"
            )

            if submit_header:

                upsert_recap_header(
                    recap_date=recap_date,
                    recap_title=recap_title,
                    recap_summary=recap_summary,
                    recap_html=recap_html
                )

                st.success("Récap enregistré.")
                st.cache_data.clear()
                st.rerun()

    # ==================================================
    # FORMULAIRE AJOUT LIGNE
    # ==================================================

    with st.expander("➕ Ajouter une ligne avec image"):

        with st.form("form_solar_recap_item"):

            item_recap_date = st.date_input(
                "Date du récap concerné",
                value=selected_recap_date,
                key="item_recap_date"
            )

            order_index = st.number_input(
                "Ordre d'affichage",
                min_value=1,
                value=1,
                step=1,
                key="item_order_index"
            )

            uploaded_image = st.file_uploader(
                "Image",
                type=["png", "jpg", "jpeg"],
                key="item_image_upload"
            )

            title = st.text_input(
                "Titre",
                placeholder="Exemple : Sites dégradés",
                key="item_title"
            )

            kpi_name = st.text_input(
                "Indicateur",
                placeholder="Exemple : Production 10 derniers jours",
                key="item_kpi_name"
            )

            kpi_value = st.text_input(
                "Valeur",
                placeholder="Exemple : 1 250",
                key="item_kpi_value"
            )

            unit = st.text_input(
                "Unité",
                placeholder="kWh / sites / %",
                key="item_unit"
            )

            status = st.selectbox(
                "Statut",
                [
                    "OK",
                    "WARNING",
                    "CRITICAL",
                    "INFO",
                ],
                key="item_status"
            )

            comment = st.text_area(
                "Commentaire",
                placeholder="Exemple : 12 sites ont une production inférieure à 60% du target.",
                key="item_comment"
            )

            submit_item = st.form_submit_button(
                "✅ Ajouter la ligne"
            )

            if submit_item:

                recap_id = upsert_recap_header(
                    recap_date=item_recap_date,
                    recap_title=f"Récap solaire du {item_recap_date}",
                    recap_summary=""
                )

                image_name, image_mime, image_base64 = file_to_base64(
                    uploaded_image
                )

                insert_recap_item(
                    recap_id=recap_id,
                    order_index=order_index,
                    image_name=image_name,
                    image_mime=image_mime,
                    image_base64=image_base64,
                    title=title,
                    kpi_name=kpi_name,
                    kpi_value=kpi_value,
                    unit=unit,
                    status=status,
                    comment=comment
                )

                st.success("Ligne ajoutée avec succès.")
                st.cache_data.clear()
                st.rerun()