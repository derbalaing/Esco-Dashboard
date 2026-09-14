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
    "local_chart.php?id=143&sa_id=2093"
    "&country=Ivory%20Coast"
    "&radio_period=radio_period_07"
)

OUTPUT_FILE = BASE_DIR / "ABG004_GridMeter_Juillet_2026.xlsx"
RAW_CSV_FILE = BASE_DIR / "ABG004_Highcharts_RAW_Juillet.csv"

DATE_START = pd.Timestamp("2026-07-01 00:00:00")
DATE_END = pd.Timestamp("2026-08-01 00:00:00")

# Format confirmé par le diagnostic EFMS
EFMS_DATE_START = "01-07-2026"
EFMS_DATE_END = "31-07-2026"

# EFMS écrit "Curent" avec un seul R
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

def get_chart_frame(page, timeout_ms=30000):
    try:
        iframe = page.locator("iframe#if_objects")
        iframe.wait_for(state="attached", timeout=timeout_ms)
    except Exception:
        print("ERREUR : iframe#if_objects introuvable.")
        print("URL principale :", page.url)
        return None

    for _ in range(120):
        for frame in page.frames:
            if (
                "global_chart.php" in frame.url
                or "global_chart2.php" in frame.url
            ):
                return frame

        page.wait_for_timeout(500)

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

        browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            storage_state=str(STATE_FILE),
            viewport={"width": 1800, "height": 1000}
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
                print("ERREUR : graphique EFMS introuvable.")
                return

            print("OK - iframe graphique trouvé.")
            print("URL iframe initiale :")
            print(frame.url)

            # ------------------------------------------------
            # 2 - FORCER LA PERIODE CUSTOM
            # ------------------------------------------------
            print("\n2 - Injection de la période Custom juillet 2026...")

            info = frame.evaluate(
                """
                ({dateStart, dateEnd}) => {
                    const form = document.getElementById('search');

                    if (!form) {
                        throw new Error('Formulaire #search introuvable');
                    }

                    const start = document.getElementById('date_no_start');
                    const end = document.getElementById('date_no_end');
                    const period = document.getElementById('custom_period_1');

                    if (!start || !end || !period) {
                        throw new Error(
                            'Champs date EFMS introuvables'
                        );
                    }

                    start.value = dateStart;
                    end.value = dateEnd;
                    period.value = 'custom';

                    // Supprimer radio_period=radio_period_07
                    // de l'action du formulaire.
                    const url = new URL(window.location.href);
                    url.searchParams.delete('radio_period');
                    form.action = url.toString();

                    return {
                        date_no_start: start.value,
                        date_no_end: end.value,
                        custom_period_1: period.value,
                        method: form.method,
                        action: form.action
                    };
                }
                """,
                {
                    "dateStart": EFMS_DATE_START,
                    "dateEnd": EFMS_DATE_END
                }
            )

            print("date_no_start   =", repr(info["date_no_start"]))
            print("date_no_end     =", repr(info["date_no_end"]))
            print("custom_period_1 =", repr(info["custom_period_1"]))
            print("method          =", repr(info["method"]))
            print("action corrigée =", info["action"])

            # ------------------------------------------------
            # 3 - SUBMIT
            # ------------------------------------------------
            print("\n3 - Envoi de la recherche EFMS...")

            frame.locator("#search").evaluate(
                "(form) => form.submit()"
            )

            # Une période d'un mois est lourde.
            page.wait_for_timeout(12000)

            frame = get_chart_frame(page)

            if frame is None:
                print("ERREUR : iframe perdu après Search.")
                return

            print("URL iframe après Search :")
            print(frame.url)

            # ------------------------------------------------
            # 4 - HIGHCHARTS
            # ------------------------------------------------
            print("\n4 - Attente Highcharts...")

            wait_for_highcharts(frame)

            print("OK - Highcharts chargé.")

            chart_start, chart_end, series_count = get_chart_range(frame)

            print("\nPériode réellement reçue de EFMS :")
            print("Début :", chart_start)
            print("Fin   :", chart_end)
            print("Nombre total de séries :", series_count)

            # Vérification souple :
            # la plage doit couvrir juillet.
            period_ok = (
                pd.notna(chart_start)
                and pd.notna(chart_end)
                and chart_start <= pd.Timestamp("2026-07-02 00:00:00")
                and chart_end >= pd.Timestamp("2026-07-31 00:00:00")
                and chart_start < DATE_END
            )

            if not period_ok:
                print()
                print("ERREUR : EFMS n'a toujours pas renvoyé juillet 2026.")
                print("Aucun Excel vide ne sera créé.")
                return

            # ------------------------------------------------
            # 5 - 6 SERIES GRID METER
            # ------------------------------------------------
            print("\n5 - Sélection des 3 tensions + 3 courants...")

            selected = select_six_grid_series(frame)

            print(f"{len(selected)} série(s) trouvée(s) :")

            for name in selected:
                print("   -", name)

            if len(selected) != 6:
                print("ERREUR : les 6 séries n'ont pas toutes été trouvées.")
                return

            # ------------------------------------------------
            # 6 - EXPORT NATIF HIGHCHARTS
            # ------------------------------------------------
            print("\n6 - Export CSV Highcharts...")

            csv_text = get_highcharts_csv(frame)

            if not csv_text or len(csv_text.strip()) < 20:
                print("ERREUR : CSV Highcharts vide.")
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

            print("Nombre de lignes brutes :", len(df_raw))

            # ------------------------------------------------
            # 7 - COLONNES
            # ------------------------------------------------
            found, missing = find_target_columns(df_raw)

            print("\nColonnes trouvées :")

            for output_name, source_col in found.items():
                print(f"OK : {output_name}")
                print(f"     -> {source_col}")

            if missing:
                print("\nColonnes manquantes :")
                for name in missing:
                    print("   -", name)

            if len(found) != 6:
                print("ERREUR : une ou plusieurs colonnes manquent.")
                return

            # ------------------------------------------------
            # 8 - DATAFRAME FINAL
            # ------------------------------------------------
            print("\n7 - Construction du fichier Excel...")

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

            # Filtre de sécurité juillet uniquement.
            df_final = df_final[
                (df_final["Date/Heure"] >= DATE_START)
                & (df_final["Date/Heure"] < DATE_END)
            ].copy()

            df_final.sort_values(
                "Date/Heure",
                inplace=True
            )

            df_final.reset_index(
                drop=True,
                inplace=True
            )

            df_final.insert(0, "Site", "ABG004")

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

            df_final = df_final[final_columns]

            print("\nRESULTAT FINAL")
            print("Nombre de lignes :", len(df_final))

            if len(df_final) == 0:
                print("ERREUR : aucune ligne juillet après filtrage.")
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
            print(df_final.head(5).to_string(index=False))

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