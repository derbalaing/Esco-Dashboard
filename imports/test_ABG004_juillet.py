from pathlib import Path
from io import StringIO

import pandas as pd
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "efms_state.json"

URL = (
    "https://efms-ivorycoast.camusat.com/"
    "local_chart.php?id=143&sa_id=4460"
    "&country=Ivory%20Coast"
    "&radio_period=radio_period_07"
)

OUTPUT_FILE = BASE_DIR / "ABG004_GridMeter_Juillet_2026.xlsx"
RAW_CSV_FILE = BASE_DIR / "ABG004_Highcharts_RAW_Juillet.csv"

DATE_START = pd.Timestamp("2026-07-01 00:00:00")
DATE_END = pd.Timestamp("2026-08-01 00:00:00")

# Format réellement observé dans EFMS
EFMS_DATE_START = "01-07-2026"
EFMS_DATE_END = "31-07-2026"

# EFMS écrit "Curent" avec un seul R.
TARGETS = {
    "Voltage L1 (V)": "Voltage L1 - N (GRID)",
    "Voltage L2 (V)": "Voltage L2 - N (GRID)",
    "Voltage L3 (V)": "Voltage L3 - N (GRID)",
    "Current L1 (A)": "Curent L1 (GRID)",
    "Current L2 (A)": "Curent L2 (GRID)",
    "Current L3 (A)": "Curent L3 (GRID)",
}


# ============================================================
# OUTILS
# ============================================================

def get_chart_frame(page, timeout_ms=60000):
    """
    Retourne LA frame de iframe#if_objects seulement lorsqu'elle
    contient réellement le formulaire EFMS #search.

    Cela évite de prendre une frame transitoire/stale qui a déjà
    l'URL global_chart.php mais dont le DOM n'est pas encore chargé.
    """
    print("\nRecherche de la frame graphique EFMS...")

    iframe_locator = page.locator("iframe#if_objects")

    try:
        iframe_locator.wait_for(
            state="attached",
            timeout=timeout_ms
        )
    except Exception:
        print("ERREUR : iframe#if_objects introuvable.")
        print("URL principale :", page.url)
        return None

    deadline_steps = max(1, timeout_ms // 500)

    for _ in range(deadline_steps):

        try:
            handle = iframe_locator.element_handle()

            if handle is not None:
                frame = handle.content_frame()

                if frame is not None:
                    url = frame.url or ""

                    if (
                        "global_chart.php" in url
                        or "global_chart2.php" in url
                    ):
                        try:
                            form = frame.locator("form#search")
                            form.wait_for(
                                state="attached",
                                timeout=1000
                            )

                            # Vérifier aussi les 3 champs date.
                            required = [
                                "#date_no_start",
                                "#date_no_end",
                                "#custom_period_1",
                            ]

                            if all(
                                frame.locator(sel).count() > 0
                                for sel in required
                            ):
                                print("Frame correcte trouvée.")
                                return frame

                        except Exception:
                            pass

        except Exception:
            pass

        page.wait_for_timeout(500)

    print("ERREUR : global_chart est visible, mais le formulaire #search")
    print("n'a pas été trouvé dans l'iframe après attente.")
    print("\nFrames connues :")

    for i, f in enumerate(page.frames):
        print(f"  {i}: {f.url}")

    return None


def wait_for_highcharts(frame):
    frame.wait_for_function(
        """
        () => {
            if (typeof Highcharts === 'undefined') return false;
            if (!Highcharts.charts) return false;

            return Highcharts.charts.some(
                c => c && c.renderTo && c.renderTo.id === 'container'
            );
        }
        """,
        timeout=180000
    )


def get_chart_range(frame):
    info = frame.evaluate(
        """
        () => {
            const chart =
                Highcharts.charts.find(
                    c => c && c.renderTo && c.renderTo.id === 'container'
                );

            if (!chart) {
                throw new Error('Graphique Highcharts introuvable');
            }

            return {
                min: chart.xAxis[0].dataMin,
                max: chart.xAxis[0].dataMax,
                seriesCount: chart.series.length
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

    return start, end, info["seriesCount"]


def set_hidden_value(frame, selector, value):
    """
    Change un input caché comme le ferait l'interface EFMS.
    """
    frame.locator(selector).evaluate(
        """
        (el, value) => {
            el.value = value;
            el.setAttribute('value', value);
            el.dispatchEvent(
                new Event('input', { bubbles: true })
            );
            el.dispatchEvent(
                new Event('change', { bubbles: true })
            );
        }
        """,
        value
    )


def select_six_grid_series(frame):
    return frame.evaluate(
        """
        (targets) => {
            const chart =
                Highcharts.charts.find(
                    c => c && c.renderTo && c.renderTo.id === 'container'
                );

            if (!chart) {
                throw new Error('Graphique Highcharts introuvable');
            }

            const needles = Object.values(targets);
            const selected = [];

            chart.series.forEach(s => {
                const name = s.name || '';

                const wanted = needles.some(
                    needle =>
                        name.toLowerCase().includes(
                            needle.toLowerCase()
                        )
                );

                s.setVisible(wanted, false);

                if (wanted) {
                    selected.push(name);
                }
            });

            chart.redraw();
            return selected;
        }
        """,
        TARGETS
    )


def get_highcharts_csv(frame):
    return frame.evaluate(
        """
        () => {
            const chart =
                Highcharts.charts.find(
                    c => c && c.renderTo && c.renderTo.id === 'container'
                );

            if (!chart) {
                throw new Error('Graphique Highcharts introuvable');
            }

            if (typeof chart.getCSV !== 'function') {
                throw new Error(
                    'chart.getCSV() indisponible'
                );
            }

            return chart.getCSV(false);
        }
        """
    )


def find_target_columns(df):
    found = {}
    missing = []

    for output_name, needle in TARGETS.items():

        matches = [
            col for col in df.columns
            if needle.lower() in str(col).lower()
        ]

        if matches:
            found[output_name] = matches[0]
        else:
            missing.append(output_name)

    return found, missing


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("=" * 72)
    print("EFMS - ABG004 - AC GRID METER")
    print("Période demandée : 01/07/2026 -> 31/07/2026")
    print("=" * 72)

    if not STATE_FILE.exists():
        print("\nSession EFMS absente.")
        print(r"Lancez d'abord : python imports\efms_login.py")
        return

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context(
            storage_state=str(STATE_FILE),
            viewport={
                "width": 1800,
                "height": 1000
            }
        )

        page = context.new_page()

        try:
            # ------------------------------------------------
            # 1 - OUVERTURE
            # ------------------------------------------------
            print("\n1 - Ouverture ABG004...")

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            page.wait_for_timeout(3000)

            frame = get_chart_frame(page)

            if frame is None:
                print("ERREUR : graphique/formulaire EFMS introuvable.")
                return

            print("OK - iframe et formulaire EFMS trouvés.")
            print("URL iframe initiale :")
            print(frame.url)

            # ------------------------------------------------
            # 2 - REPRODUIRE EXACTEMENT LE CUSTOM MANUEL
            # ------------------------------------------------
            #
            # IMPORTANT :
            # Nous NE MODIFIONS PLUS form.action et nous NE SUPPRIMONS
            # PLUS radio_period=radio_period_07.
            #
            # Le diagnostic manuel a montré que l'interface fonctionne
            # avec cette URL, mais en envoyant les 3 valeurs POST :
            #
            # date_no_start   = 01-07-2026
            # date_no_end     = 31-07-2026
            # custom_period_1 = custom
            #
            # ------------------------------------------------
            print("\n2 - Injection exacte de la période Custom...")

            set_hidden_value(
                frame,
                "#date_no_start",
                EFMS_DATE_START
            )

            set_hidden_value(
                frame,
                "#date_no_end",
                EFMS_DATE_END
            )

            set_hidden_value(
                frame,
                "#custom_period_1",
                "custom"
            )

            # Vérification juste avant POST
            form_info = frame.evaluate(
                """
                () => {
                    const form =
                        document.querySelector('form#search');

                    if (!form) {
                        throw new Error(
                            'Formulaire #search introuvable'
                        );
                    }

                    return {
                        start:
                            document.getElementById(
                                'date_no_start'
                            ).value,

                        end:
                            document.getElementById(
                                'date_no_end'
                            ).value,

                        period:
                            document.getElementById(
                                'custom_period_1'
                            ).value,

                        method: form.method,

                        // On n'affiche pas l'action ici car
                        // l'URL peut contenir un hash de session.
                        hasForm: true
                    };
                }
                """
            )

            print(
                "date_no_start   =",
                repr(form_info["start"])
            )
            print(
                "date_no_end     =",
                repr(form_info["end"])
            )
            print(
                "custom_period_1 =",
                repr(form_info["period"])
            )
            print(
                "method          =",
                repr(form_info["method"])
            )

            if (
                form_info["start"] != EFMS_DATE_START
                or form_info["end"] != EFMS_DATE_END
                or form_info["period"] != "custom"
            ):
                print("ERREUR : les valeurs Custom n'ont pas été injectées.")
                return

            # ------------------------------------------------
            # 3 - SUBMIT IDENTIQUE AU BOUTON SEARCH
            # ------------------------------------------------
            print("\n3 - Envoi du formulaire EFMS...")

            # Le source EFMS utilise :
            # document.getElementById('search').submit()
            frame.locator("form#search").evaluate(
                "(form) => form.submit()"
            )

            # Attendre le mois complet.
            page.wait_for_timeout(12000)

            # Reprendre la frame APRES navigation.
            frame = get_chart_frame(
                page,
                timeout_ms=120000
            )

            if frame is None:
                print("ERREUR : iframe/formulaire perdu après Search.")
                return

            # ------------------------------------------------
            # 4 - HIGHCHARTS
            # ------------------------------------------------
            print("\n4 - Attente Highcharts...")

            wait_for_highcharts(frame)

            print("OK - Highcharts chargé.")

            chart_start, chart_end, series_count = get_chart_range(
                frame
            )

            print("\nPériode réellement reçue de EFMS :")
            print("Début :", chart_start)
            print("Fin   :", chart_end)
            print(
                "Nombre total de séries :",
                series_count
            )

            # On veut une plage qui couvre réellement juillet.
            period_ok = (
                pd.notna(chart_start)
                and pd.notna(chart_end)
                and chart_start <= pd.Timestamp(
                    "2026-07-02 00:00:00"
                )
                and chart_end >= pd.Timestamp(
                    "2026-07-31 00:00:00"
                )
                and chart_start < DATE_END
            )

            if not period_ok:
                print()
                print(
                    "ERREUR : EFMS n'a pas renvoyé "
                    "la période de juillet."
                )
                print(
                    "Le script n'écrira pas un Excel vide."
                )
                return

            # ------------------------------------------------
            # 5 - 6 SERIES GRID
            # ------------------------------------------------
            print(
                "\n5 - Sélection des 3 tensions "
                "+ 3 courants..."
            )

            selected = select_six_grid_series(
                frame
            )

            print(
                f"{len(selected)} série(s) trouvée(s) :"
            )

            for name in selected:
                print("   -", name)

            if len(selected) != 6:
                print(
                    "ERREUR : les 6 séries Grid "
                    "n'ont pas toutes été trouvées."
                )
                return

            # ------------------------------------------------
            # 6 - CSV
            # ------------------------------------------------
            print("\n6 - Export CSV Highcharts...")

            csv_text = get_highcharts_csv(frame)

            if (
                not csv_text
                or len(csv_text.strip()) < 20
            ):
                print(
                    "ERREUR : CSV Highcharts vide."
                )
                return

            RAW_CSV_FILE.write_text(
                csv_text,
                encoding="utf-8"
            )

            print("CSV brut sauvegardé :")
            print(RAW_CSV_FILE.resolve())

            df_raw = pd.read_csv(
                StringIO(csv_text),
                sep=None,
                engine="python"
            )

            print(
                "Nombre de lignes brutes :",
                len(df_raw)
            )

            # ------------------------------------------------
            # 7 - COLONNES
            # ------------------------------------------------
            found, missing = find_target_columns(
                df_raw
            )

            print("\nColonnes trouvées :")

            for output_name, source_col in found.items():
                print(f"OK : {output_name}")
                print(f"     -> {source_col}")

            if missing:
                print("\nColonnes manquantes :")

                for name in missing:
                    print("   -", name)

            if len(found) != 6:
                print(
                    "ERREUR : une ou plusieurs "
                    "colonnes Grid manquent."
                )
                return

            # ------------------------------------------------
            # 8 - TABLEAU FINAL
            # ------------------------------------------------
            print(
                "\n7 - Construction du fichier Excel..."
            )

            date_col = df_raw.columns[0]

            df_final = pd.DataFrame()

            df_final["Date/Heure"] = pd.to_datetime(
                df_raw[date_col],
                errors="coerce"
            )

            for output_name, source_col in found.items():

                df_final[output_name] = pd.to_numeric(
                    df_raw[source_col],
                    errors="coerce"
                )

            df_final = df_final[
                (
                    df_final["Date/Heure"]
                    >= DATE_START
                )
                &
                (
                    df_final["Date/Heure"]
                    < DATE_END
                )
            ].copy()

            df_final.sort_values(
                "Date/Heure",
                inplace=True
            )

            df_final.reset_index(
                drop=True,
                inplace=True
            )

            df_final.insert(
                0,
                "Site",
                "ABG004"
            )

            final_columns = [
                "Site",
                "Date/Heure",
                "Voltage L1 (V)",
                "Voltage L2 (V)",
                "Voltage L3 (V)",
                "Current L1 (A)",
                "Current L2 (A)",
                "Current L3 (A)",
            ]

            df_final = df_final[
                final_columns
            ]

            print("\nRESULTAT FINAL")
            print(
                "Nombre de lignes :",
                len(df_final)
            )

            if len(df_final) == 0:
                print(
                    "ERREUR : aucune ligne juillet "
                    "après filtrage."
                )
                return

            print(
                "Première mesure :",
                df_final["Date/Heure"].min()
            )

            print(
                "Dernière mesure :",
                df_final["Date/Heure"].max()
            )

            print("\nPremières lignes :")
            print(
                df_final.head(5).to_string(
                    index=False
                )
            )

            # ------------------------------------------------
            # 9 - EXCEL
            # ------------------------------------------------
            with pd.ExcelWriter(
                OUTPUT_FILE,
                engine="openpyxl"
            ) as writer:

                df_final.to_excel(
                    writer,
                    sheet_name="Grid Meter",
                    index=False
                )

                summary = pd.DataFrame(
                    {
                        "Information": [
                            "Site",
                            "Période demandée",
                            "Période EFMS début",
                            "Période EFMS fin",
                            "Nombre de lignes",
                        ],
                        "Valeur": [
                            "ABG004",
                            "01/07/2026 - 31/07/2026",
                            chart_start,
                            chart_end,
                            len(df_final),
                        ]
                    }
                )

                summary.to_excel(
                    writer,
                    sheet_name="Résumé",
                    index=False
                )

            print("\nFICHIER EXCEL CREE :")
            print(OUTPUT_FILE.resolve())

            context.storage_state(
                path=str(STATE_FILE)
            )

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()