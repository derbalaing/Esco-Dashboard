from pathlib import Path
from io import StringIO
from math import ceil
import time

import pandas as pd
from playwright.sync_api import sync_playwright


# ============================================================
# CHEMINS
# ============================================================

IMPORTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = IMPORTS_DIR.parent

INPUT_XLSX = IMPORTS_DIR / "Liste_Sites_EFMS.xlsx"
PROFILE_DIR = PROJECT_DIR / "efms_unique_profile"

HOME_URL = "https://efms-ivorycoast.camusat.com/"

# Page de départ déjà validée avec ABG004.
START_URL = (
    "https://efms-ivorycoast.camusat.com/"
    "local_chart.php?id=143&sa_id=2093"
    "&country=Ivory%20Coast"
    "&radio_period=radio_period_07"
)

TARGETS = {
    "Voltage L1 (V)": "Voltage L1 - N (GRID)",
    "Voltage L2 (V)": "Voltage L2 - N (GRID)",
    "Voltage L3 (V)": "Voltage L3 - N (GRID)",
    "Current L1 (A)": "Curent L1 (GRID)",
    "Current L2 (A)": "Curent L2 (GRID)",
    "Current L3 (A)": "Curent L3 (GRID)",
}

EXCEL_MAX_DATA_ROWS = 900_000


# ============================================================
# CONFIGURATION EXCEL
# ============================================================

def read_input_file():
    if not INPUT_XLSX.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {INPUT_XLSX}"
        )

    sites_df = pd.read_excel(
        INPUT_XLSX,
        sheet_name="Sites"
    )

    if "Site" not in sites_df.columns:
        raise ValueError(
            "L'onglet Sites doit contenir une colonne 'Site'."
        )

    if "Actif" in sites_df.columns:
        actif = (
            sites_df["Actif"]
            .fillna("Oui")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        sites_df = sites_df[
            ~actif.isin(
                ["non", "no", "false", "0"]
            )
        ]

    sites = (
        sites_df["Site"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
    )

    sites = [
        s for s in sites
        if s
    ]

    # Supprimer doublons sans changer l'ordre.
    sites = list(dict.fromkeys(sites))

    cfg_df = pd.read_excel(
        INPUT_XLSX,
        sheet_name="Configuration"
    )

    if not {
        "Paramètre",
        "Valeur"
    }.issubset(cfg_df.columns):
        raise ValueError(
            "L'onglet Configuration doit contenir "
            "'Paramètre' et 'Valeur'."
        )

    cfg = dict(
        zip(
            cfg_df["Paramètre"].astype(str),
            cfg_df["Valeur"]
        )
    )

    date_start = pd.Timestamp(
        cfg.get("Date début")
    ).normalize()

    date_end_inclusive = pd.Timestamp(
        cfg.get("Date fin")
    ).normalize()

    if pd.isna(date_start) or pd.isna(date_end_inclusive):
        raise ValueError(
            "Date début / Date fin invalides."
        )

    if date_end_inclusive < date_start:
        raise ValueError(
            "Date fin doit être >= Date début."
        )

    export_folder_name = str(
        cfg.get(
            "Dossier export",
            "exports_EFMS"
        )
    ).strip()

    export_individuel = str(
        cfg.get(
            "Export individuel",
            "Oui"
        )
    ).strip().lower() not in [
        "non",
        "no",
        "false",
        "0",
    ]

    export_global_excel = str(
        cfg.get(
            "Export global Excel",
            "Oui"
        )
    ).strip().lower() not in [
        "non",
        "no",
        "false",
        "0",
    ]

    export_global_csv = str(
        cfg.get(
            "Export global CSV",
            "Oui"
        )
    ).strip().lower() not in [
        "non",
        "no",
        "false",
        "0",
    ]

    try:
        pause_seconds = int(
            float(
                cfg.get(
                    "Pause chargement (s)",
                    8
                )
            )
        )
    except Exception:
        pause_seconds = 8

    return {
        "sites": sites,
        "date_start": date_start,
        "date_end_inclusive": date_end_inclusive,
        "date_end_exclusive": (
            date_end_inclusive
            + pd.Timedelta(days=1)
        ),
        "efms_date_start": date_start.strftime(
            "%d-%m-%Y"
        ),
        "efms_date_end": date_end_inclusive.strftime(
            "%d-%m-%Y"
        ),
        "export_folder_name": export_folder_name,
        "export_individuel": export_individuel,
        "export_global_excel": export_global_excel,
        "export_global_csv": export_global_csv,
        "pause_seconds": max(
            3,
            pause_seconds
        ),
    }


# ============================================================
# SESSION / NAVIGATEUR
# ============================================================

def simultaneous_login(page):
    try:
        if (
            "access_denied.php" in page.url
            and "mess=sim" in page.url
        ):
            return True

        text = page.locator(
            "body"
        ).inner_text(
            timeout=3000
        )

        return (
            "Simultaneous logins" in text
            or
            "Your session is terminated" in text
        )

    except Exception:
        return False


def login_page(page):
    try:
        return (
            page.locator(
                'input[type="password"]'
            ).count()
            > 0
        )
    except Exception:
        return False


def get_chart_frame(
    page,
    timeout_ms=120000
):
    iframe = page.locator(
        "iframe#if_objects"
    )

    try:
        iframe.wait_for(
            state="attached",
            timeout=timeout_ms
        )
    except Exception:
        return None

    for _ in range(
        max(
            1,
            timeout_ms // 500
        )
    ):
        try:
            handle = (
                iframe.element_handle()
            )

            if handle is not None:
                frame = (
                    handle.content_frame()
                )

                if frame is not None:
                    url = frame.url or ""

                    if (
                        "global_chart.php"
                        in url
                        or
                        "global_chart2.php"
                        in url
                    ):
                        if (
                            frame.locator(
                                "form#search"
                            ).count()
                            > 0
                            and
                            frame.locator(
                                "#country"
                            ).count()
                            > 0
                        ):
                            return frame

        except Exception:
            pass

        page.wait_for_timeout(
            500
        )

    return None


# ============================================================
# MAPPING SITE -> sa_id
# ============================================================

def load_sites_filter(frame):
    frame.evaluate(
        """
        () => {
            const country =
                document.getElementById(
                    'country'
                );

            if (!country) {
                throw new Error(
                    '#country introuvable'
                );
            }

            country.value =
                'Ivory Coast';

            country.dispatchEvent(
                new Event(
                    'change',
                    { bubbles: true }
                )
            );
        }
        """
    )

    frame.wait_for_function(
        """
        () => {
            const box =
                document.getElementById(
                    'td_1_2'
                );

            if (!box) return false;

            return (
                box.querySelector(
                    'input.client_checkboxes[id^="chk_site_"]'
                )
                !== null
                ||
                (box.innerHTML || '')
                    .includes(
                        'chk_site_'
                    )
            );
        }
        """,
        timeout=120000
    )

    frame.wait_for_timeout(
        1200
    )


def map_sites(
    frame,
    site_codes
):
    return frame.evaluate(
        """
        (targets) => {
            const box =
                document.getElementById(
                    'td_1_2'
                );

            if (!box) {
                throw new Error(
                    '#td_1_2 introuvable'
                );
            }

            const checks =
                Array.from(
                    box.querySelectorAll(
                        'input.client_checkboxes[id^="chk_site_"]'
                    )
                );

            const results = {};

            for (
                const original
                of targets
            ) {
                const target =
                    String(
                        original
                    )
                    .trim()
                    .toUpperCase();

                const el =
                    checks.find(
                        c =>
                            String(
                                c.value || ''
                            )
                            .trim()
                            .toUpperCase()
                            === target
                    );

                if (!el) {
                    results[
                        original
                    ] = {
                        found: false,
                        sa_id: null,
                        checkbox_id: null
                    };

                    continue;
                }

                results[
                    original
                ] = {
                    found: true,
                    sa_id:
                        el.id.replace(
                            /^chk_site_/,
                            ''
                        ),
                    checkbox_id:
                        el.id
                };
            }

            return {
                checkbox_count:
                    checks.length,
                results:
                    results
            };
        }
        """,
        site_codes
    )


# ============================================================
# POST SITE + PERIODE
# ============================================================

def prepare_site_and_period_post(
    frame,
    site_code,
    sa_id,
    checkbox_id,
    efms_date_start,
    efms_date_end,
):
    return frame.evaluate(
        """
        (args) => {

            const form =
                document.querySelector(
                    'form#search'
                );

            if (!form) {
                throw new Error(
                    'form#search introuvable'
                );
            }

            const target =
                document.getElementById(
                    args.checkboxId
                );

            const hiddenSa =
                document.getElementById(
                    'sa_id'
                );

            const dateStart =
                document.getElementById(
                    'date_no_start'
                );

            const dateEnd =
                document.getElementById(
                    'date_no_end'
                );

            const period =
                document.getElementById(
                    'custom_period_1'
                );

            if (
                !target
                || !hiddenSa
                || !dateStart
                || !dateEnd
                || !period
            ) {
                throw new Error(
                    'Un champ EFMS nécessaire est introuvable'
                );
            }

            document
                .querySelectorAll(
                    'input.client_checkboxes'
                )
                .forEach(
                    el => {
                        el.checked =
                            false;

                        el.removeAttribute(
                            'checked'
                        );
                    }
                );

            target.checked =
                true;

            target.setAttribute(
                'checked',
                'checked'
            );

            hiddenSa.value =
                String(
                    args.saId
                );

            hiddenSa.setAttribute(
                'value',
                String(
                    args.saId
                )
            );

            dateStart.value =
                args.dateStart;

            dateStart.setAttribute(
                'value',
                args.dateStart
            );

            dateEnd.value =
                args.dateEnd;

            dateEnd.setAttribute(
                'value',
                args.dateEnd
            );

            period.value =
                'custom';

            period.setAttribute(
                'value',
                'custom'
            );

            const fd =
                new FormData(
                    form
                );

            const selectedSites =
                [];

            for (
                const [name, value]
                of fd.entries()
            ) {
                if (
                    String(name)
                        .startsWith(
                            'chk_site_'
                        )
                ) {
                    selectedSites.push(
                        {
                            name:
                                String(name),

                            value:
                                String(value)
                        }
                    );
                }
            }

            return {
                sa_id:
                    hiddenSa.value,

                start:
                    dateStart.value,

                end:
                    dateEnd.value,

                period:
                    period.value,

                selected_sites:
                    selectedSites
            };
        }
        """,
        {
            "siteCode":
                site_code,

            "saId":
                sa_id,

            "checkboxId":
                checkbox_id,

            "dateStart":
                efms_date_start,

            "dateEnd":
                efms_date_end,
        }
    )


def submit_search_form(
    frame
):
    frame.locator(
        "form#search"
    ).evaluate(
        "(form) => form.submit()"
    )


# ============================================================
# HIGHCHARTS / EXTRACTION
# ============================================================

def wait_for_highcharts(
    frame
):
    frame.wait_for_function(
        """
        () => {
            if (
                typeof Highcharts
                === 'undefined'
            ) {
                return false;
            }

            if (
                !Highcharts.charts
            ) {
                return false;
            }

            return (
                Highcharts.charts.some(
                    c =>
                        c
                        && c.renderTo
                        && c.renderTo.id
                            === 'container'
                )
            );
        }
        """,
        timeout=180000
    )


def displayed_site(
    frame
):
    try:
        link = frame.locator(
            'a[href*="sites.php"]'
        ).first

        if (
            link.count()
            > 0
        ):
            return (
                link.inner_text()
                .strip()
            )
    except Exception:
        pass

    return ""


def get_chart_range(
    frame
):
    info = frame.evaluate(
        """
        () => {
            const chart =
                Highcharts.charts.find(
                    c =>
                        c
                        && c.renderTo
                        && c.renderTo.id
                            === 'container'
                );

            if (!chart) {
                throw new Error(
                    'Graphique Highcharts introuvable'
                );
            }

            return {
                min:
                    chart.xAxis[0].dataMin,
                max:
                    chart.xAxis[0].dataMax,
                seriesCount:
                    chart.series.length
            };
        }
        """
    )

    start = pd.to_datetime(
        info["min"],
        unit="ms",
        errors="coerce"
    )

    end = pd.to_datetime(
        info["max"],
        unit="ms",
        errors="coerce"
    )

    return (
        start,
        end,
        info[
            "seriesCount"
        ],
    )


def select_six_grid_series(
    frame
):
    return frame.evaluate(
        """
        (targets) => {

            const chart =
                Highcharts.charts.find(
                    c =>
                        c
                        && c.renderTo
                        && c.renderTo.id
                            === 'container'
                );

            if (!chart) {
                throw new Error(
                    'Graphique Highcharts introuvable'
                );
            }

            const needles =
                Object.values(
                    targets
                );

            const selected =
                [];

            chart.series.forEach(
                s => {
                    const name =
                        s.name || '';

                    const wanted =
                        needles.some(
                            needle =>
                                name
                                    .toLowerCase()
                                    .includes(
                                        needle
                                            .toLowerCase()
                                    )
                        );

                    s.setVisible(
                        wanted,
                        false
                    );

                    if (wanted) {
                        selected.push(
                            name
                        );
                    }
                }
            );

            chart.redraw();

            return selected;
        }
        """,
        TARGETS
    )


def get_highcharts_csv(
    frame
):
    return frame.evaluate(
        """
        () => {
            const chart =
                Highcharts.charts.find(
                    c =>
                        c
                        && c.renderTo
                        && c.renderTo.id
                            === 'container'
                );

            if (!chart) {
                throw new Error(
                    'Graphique Highcharts introuvable'
                );
            }

            if (
                typeof chart.getCSV
                !== 'function'
            ) {
                throw new Error(
                    'chart.getCSV() indisponible'
                );
            }

            return chart.getCSV(
                false
            );
        }
        """
    )


def find_target_columns(
    df
):
    found = {}
    missing = []

    for (
        output_name,
        needle
    ) in TARGETS.items():

        matches = [
            col
            for col in df.columns
            if (
                needle.lower()
                in str(
                    col
                ).lower()
            )
        ]

        if matches:
            found[
                output_name
            ] = matches[0]

        else:
            missing.append(
                output_name
            )

    return (
        found,
        missing
    )


def build_final_dataframe(
    csv_text,
    site_code,
    displayed_name,
    date_start,
    date_end_exclusive,
):
    df_raw = pd.read_csv(
        StringIO(
            csv_text
        ),
        sep=None,
        engine="python"
    )

    found, missing = (
        find_target_columns(
            df_raw
        )
    )

    if missing:
        raise RuntimeError(
            "Paramètres Grid manquants : "
            + ", ".join(
                missing
            )
        )

    date_col = (
        df_raw.columns[0]
    )

    df = pd.DataFrame()

    df[
        "Date/Heure"
    ] = pd.to_datetime(
        df_raw[
            date_col
        ],
        errors="coerce"
    )

    for (
        output_name,
        source_col
    ) in found.items():

        df[
            output_name
        ] = pd.to_numeric(
            df_raw[
                source_col
            ],
            errors="coerce"
        )

    df = df[
        (
            df[
                "Date/Heure"
            ]
            >= date_start
        )
        &
        (
            df[
                "Date/Heure"
            ]
            < date_end_exclusive
        )
    ].copy()

    df.sort_values(
        "Date/Heure",
        inplace=True
    )

    df.reset_index(
        drop=True,
        inplace=True
    )

    df.insert(
        0,
        "Site",
        site_code
    )

    df.insert(
        1,
        "Nom EFMS",
        displayed_name
    )

    columns = [
        "Site",
        "Nom EFMS",
        "Date/Heure",
        "Voltage L1 (V)",
        "Voltage L2 (V)",
        "Voltage L3 (V)",
        "Current L1 (A)",
        "Current L2 (A)",
        "Current L3 (A)",
    ]

    return (
        df[
            columns
        ],
        len(
            df_raw
        ),
    )


# ============================================================
# EXPORTS
# ============================================================

def write_site_excel(
    df,
    output_file,
    site_code,
    displayed_name,
    chart_start,
    chart_end,
):
    with pd.ExcelWriter(
        output_file,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Grid Meter",
            index=False
        )

        resume = pd.DataFrame(
            {
                "Information": [
                    "Site",
                    "Nom EFMS",
                    "Période données EFMS début",
                    "Période données EFMS fin",
                    "Nombre de lignes exportées",
                ],
                "Valeur": [
                    site_code,
                    displayed_name,
                    chart_start,
                    chart_end,
                    len(df),
                ],
            }
        )

        resume.to_excel(
            writer,
            sheet_name="Résumé",
            index=False
        )

        ws = writer.book[
            "Grid Meter"
        ]

        ws.freeze_panes = (
            "A2"
        )

        for col in ws.columns:
            width = min(
                28,
                max(
                    len(
                        str(
                            cell.value
                            if cell.value
                            is not None
                            else ""
                        )
                    )
                    for cell in col
                )
                + 2,
            )

            ws.column_dimensions[
                col[0].column_letter
            ].width = width


def write_global_excel(
    all_df,
    status_df,
    output_file,
):
    with pd.ExcelWriter(
        output_file,
        engine="openpyxl"
    ) as writer:

        status_df.to_excel(
            writer,
            sheet_name="Résumé",
            index=False
        )

        if all_df.empty:
            pd.DataFrame(
                columns=[
                    "Site",
                    "Nom EFMS",
                    "Date/Heure",
                    "Voltage L1 (V)",
                    "Voltage L2 (V)",
                    "Voltage L3 (V)",
                    "Current L1 (A)",
                    "Current L2 (A)",
                    "Current L3 (A)",
                ]
            ).to_excel(
                writer,
                sheet_name="Data_001",
                index=False
            )

        else:
            n_chunks = ceil(
                len(all_df)
                / EXCEL_MAX_DATA_ROWS
            )

            for i in range(
                n_chunks
            ):
                start = (
                    i
                    * EXCEL_MAX_DATA_ROWS
                )

                end = min(
                    len(all_df),
                    (
                        i + 1
                    )
                    * EXCEL_MAX_DATA_ROWS,
                )

                chunk = (
                    all_df.iloc[
                        start:end
                    ]
                )

                chunk.to_excel(
                    writer,
                    sheet_name=(
                        f"Data_{i+1:03d}"
                    ),
                    index=False
                )


# ============================================================
# MAIN
# ============================================================

def main():
    cfg = read_input_file()

    sites = cfg["sites"]

    if not sites:
        print(
            "Aucun site actif dans Liste_Sites_EFMS.xlsx."
        )
        return

    output_root = (
        PROJECT_DIR
        / cfg[
            "export_folder_name"
        ]
        / (
            cfg[
                "date_start"
            ].strftime(
                "%Y-%m-%d"
            )
            + "_au_"
            + cfg[
                "date_end_inclusive"
            ].strftime(
                "%Y-%m-%d"
            )
        )
    )

    site_output_dir = (
        output_root
        / "Par_site"
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True
    )

    site_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 78)
    print("EFMS - EXPORT MULTI-SITES AC GRID METER")
    print("=" * 78)

    print(
        "Nombre de sites :",
        len(sites)
    )

    print(
        "Période :",
        cfg[
            "date_start"
        ].strftime(
            "%d/%m/%Y"
        ),
        "->",
        cfg[
            "date_end_inclusive"
        ].strftime(
            "%d/%m/%Y"
        ),
    )

    print(
        "Dossier export :",
        output_root
    )

    status_rows = []
    global_frames = []

    with sync_playwright() as p:

        context = (
            p.chromium
            .launch_persistent_context(
                user_data_dir=str(
                    PROFILE_DIR
                ),
                headless=False,
                viewport={
                    "width": 1800,
                    "height": 1000
                },
            )
        )

        try:
            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            # --------------------------------------------
            # LOGIN
            # --------------------------------------------
            page.goto(
                HOME_URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            page.wait_for_timeout(
                2000
            )

            if simultaneous_login(
                page
            ):
                print(
                    "ERREUR : EFMS détecte une connexion simultanée."
                )
                return

            if login_page(
                page
            ):
                print()
                print(
                    "Connectez-vous manuellement dans CETTE fenêtre EFMS."
                )

                input(
                    "Quand vous êtes connecté, appuyez sur ENTREE ici..."
                )

            # --------------------------------------------
            # CHART INITIAL
            # --------------------------------------------
            print(
                "\nOuverture du graphique EFMS..."
            )

            page.goto(
                START_URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            page.wait_for_timeout(
                3000
            )

            frame = get_chart_frame(
                page
            )

            if frame is None:
                print(
                    "ERREUR : global_chart introuvable."
                )
                return

            # --------------------------------------------
            # MAPPING TOUS LES SITES UNE FOIS
            # --------------------------------------------
            print(
                "Chargement de la liste des sites EFMS..."
            )

            load_sites_filter(
                frame
            )

            mapping_data = map_sites(
                frame,
                sites
            )

            mapping = mapping_data[
                "results"
            ]

            print(
                "Sites disponibles dans le filtre EFMS :",
                mapping_data[
                    "checkbox_count"
                ]
            )

            # --------------------------------------------
            # BOUCLE SITES
            # --------------------------------------------
            for index, site in enumerate(
                sites,
                start=1
            ):
                print()
                print(
                    "-" * 78
                )

                print(
                    f"[{index}/{len(sites)}] {site}"
                )

                result = mapping.get(
                    site,
                    {}
                )

                if not result.get(
                    "found"
                ):
                    msg = (
                        "Site non trouvé dans EFMS"
                    )

                    print(
                        "ECHEC :",
                        msg
                    )

                    status_rows.append(
                        {
                            "Site": site,
                            "sa_id": "",
                            "Nom EFMS": "",
                            "Statut": "ECHEC",
                            "Lignes": 0,
                            "Début données": "",
                            "Fin données": "",
                            "Erreur": msg,
                        }
                    )

                    continue

                sa_id = result[
                    "sa_id"
                ]

                checkbox_id = result[
                    "checkbox_id"
                ]

                try:
                    # Recharger le filtre dans le DOM courant.
                    load_sites_filter(
                        frame
                    )

                    post_info = (
                        prepare_site_and_period_post(
                            frame=frame,
                            site_code=site,
                            sa_id=sa_id,
                            checkbox_id=checkbox_id,
                            efms_date_start=cfg[
                                "efms_date_start"
                            ],
                            efms_date_end=cfg[
                                "efms_date_end"
                            ],
                        )
                    )

                    selected = (
                        post_info[
                            "selected_sites"
                        ]
                    )

                    if (
                        len(selected)
                        != 1
                        or selected[0][
                            "name"
                        ]
                        != checkbox_id
                    ):
                        raise RuntimeError(
                            "Le POST ne contient pas exactement le site cible."
                        )

                    print(
                        "sa_id :",
                        sa_id
                    )

                    print(
                        "Période envoyée :",
                        post_info[
                            "start"
                        ],
                        "->",
                        post_info[
                            "end"
                        ],
                    )

                    submit_search_form(
                        frame
                    )

                    page.wait_for_timeout(
                        cfg[
                            "pause_seconds"
                        ]
                        * 1000
                    )

                    if simultaneous_login(
                        page
                    ):
                        raise RuntimeError(
                            "Connexion simultanée détectée par EFMS."
                        )

                    frame = get_chart_frame(
                        page,
                        timeout_ms=180000
                    )

                    if frame is None:
                        raise RuntimeError(
                            "Frame global_chart introuvable après POST."
                        )

                    wait_for_highcharts(
                        frame
                    )

                    shown = displayed_site(
                        frame
                    )

                    print(
                        "Site affiché :",
                        shown
                    )

                    if (
                        not shown
                        or site.upper()
                        not in shown.upper()
                    ):
                        raise RuntimeError(
                            f"Mauvais site affiché : {shown}"
                        )

                    (
                        chart_start,
                        chart_end,
                        series_count,
                    ) = get_chart_range(
                        frame
                    )

                    print(
                        "Période reçue :",
                        chart_start,
                        "->",
                        chart_end
                    )

                    selected_series = (
                        select_six_grid_series(
                            frame
                        )
                    )

                    if (
                        len(
                            selected_series
                        )
                        != 6
                    ):
                        raise RuntimeError(
                            "Les 6 séries Grid ne sont pas toutes disponibles."
                        )

                    csv_text = (
                        get_highcharts_csv(
                            frame
                        )
                    )

                    if (
                        not csv_text
                        or len(
                            csv_text.strip()
                        )
                        < 20
                    ):
                        raise RuntimeError(
                            "CSV Highcharts vide."
                        )

                    (
                        df_site,
                        raw_rows,
                    ) = build_final_dataframe(
                        csv_text=csv_text,
                        site_code=site,
                        displayed_name=shown,
                        date_start=cfg[
                            "date_start"
                        ],
                        date_end_exclusive=cfg[
                            "date_end_exclusive"
                        ],
                    )

                    print(
                        "Lignes brutes :",
                        raw_rows
                    )

                    print(
                        "Lignes exportées :",
                        len(
                            df_site
                        )
                    )

                    if df_site.empty:
                        raise RuntimeError(
                            "Aucune donnée sur la période demandée."
                        )

                    if cfg[
                        "export_individuel"
                    ]:
                        site_file = (
                            site_output_dir
                            / (
                                f"{site}_GridMeter_"
                                f"{cfg['date_start']:%Y-%m-%d}_"
                                f"{cfg['date_end_inclusive']:%Y-%m-%d}.xlsx"
                            )
                        )

                        write_site_excel(
                            df=df_site,
                            output_file=site_file,
                            site_code=site,
                            displayed_name=shown,
                            chart_start=chart_start,
                            chart_end=chart_end,
                        )

                        print(
                            "Export individuel :",
                            site_file.name
                        )

                    global_frames.append(
                        df_site
                    )

                    status_rows.append(
                        {
                            "Site": site,
                            "sa_id": sa_id,
                            "Nom EFMS": shown,
                            "Statut": "OK",
                            "Lignes": len(
                                df_site
                            ),
                            "Début données": (
                                df_site[
                                    "Date/Heure"
                                ].min()
                            ),
                            "Fin données": (
                                df_site[
                                    "Date/Heure"
                                ].max()
                            ),
                            "Erreur": "",
                        }
                    )

                    print(
                        "RESULTAT : OK"
                    )

                except Exception as exc:
                    msg = str(
                        exc
                    )

                    print(
                        "RESULTAT : ECHEC"
                    )

                    print(
                        "Erreur :",
                        msg
                    )

                    status_rows.append(
                        {
                            "Site": site,
                            "sa_id": sa_id,
                            "Nom EFMS": "",
                            "Statut": "ECHEC",
                            "Lignes": 0,
                            "Début données": "",
                            "Fin données": "",
                            "Erreur": msg,
                        }
                    )

                    # Revenir au chart initial pour tenter le site suivant.
                    try:
                        page.goto(
                            START_URL,
                            wait_until="domcontentloaded",
                            timeout=120000
                        )

                        page.wait_for_timeout(
                            3000
                        )

                        frame = get_chart_frame(
                            page
                        )

                    except Exception:
                        frame = None

                    if frame is None:
                        print(
                            "Impossible de récupérer EFMS. Arrêt de la boucle."
                        )
                        break

            # --------------------------------------------
            # EXPORT GLOBAL
            # --------------------------------------------
            status_df = pd.DataFrame(
                status_rows
            )

            all_df = (
                pd.concat(
                    global_frames,
                    ignore_index=True
                )
                if global_frames
                else pd.DataFrame()
            )

            global_prefix = (
                output_root
                / (
                    "EFMS_GridMeter_Tous_Sites_"
                    f"{cfg['date_start']:%Y-%m-%d}_"
                    f"{cfg['date_end_inclusive']:%Y-%m-%d}"
                )
            )

            if cfg[
                "export_global_csv"
            ] and not all_df.empty:

                csv_file = (
                    global_prefix
                    .with_suffix(
                        ".csv"
                    )
                )

                all_df.to_csv(
                    csv_file,
                    index=False,
                    encoding="utf-8-sig"
                )

                print(
                    "\nCSV global :",
                    csv_file
                )

            if cfg[
                "export_global_excel"
            ]:

                xlsx_file = (
                    global_prefix
                    .with_suffix(
                        ".xlsx"
                    )
                )

                write_global_excel(
                    all_df=all_df,
                    status_df=status_df,
                    output_file=xlsx_file,
                )

                print(
                    "Excel global :",
                    xlsx_file
                )

            status_file = (
                output_root
                / "EFMS_Statut_Extraction.xlsx"
            )

            status_df.to_excel(
                status_file,
                index=False
            )

            print()
            print("=" * 78)
            print("EXTRACTION TERMINEE")
            print("=" * 78)

            ok_count = (
                status_df[
                    "Statut"
                ].eq(
                    "OK"
                ).sum()
                if not status_df.empty
                else 0
            )

            print(
                "Sites OK :",
                ok_count,
                "/",
                len(sites)
            )

            print(
                "Dossier :",
                output_root
            )

        finally:
            context.close()


if __name__ == "__main__":
    main()
