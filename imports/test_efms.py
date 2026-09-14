from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime


URL = (
    "https://efms-ivorycoast.camusat.com/"
    "local_chart.php?id=143&sa_id=2093"
    "&country=Ivory%20Coast"
    "&radio_period=radio_period_07"
)


with sync_playwright() as p:

    # Profil persistant :
    # après la première connexion, la session EFMS est conservée
    context = p.chromium.launch_persistent_context(
        user_data_dir="efms_profile",
        headless=False
    )

    page = context.pages[0] if context.pages else context.new_page()

    print("Ouverture EFMS...")

    page.goto(URL)

    # -----------------------------------------------------
    # PREMIER LANCEMENT
    # -----------------------------------------------------
    # Si EFMS demande le login,
    # connectez-vous normalement dans le navigateur.
    #
    # Les lancements suivants réutiliseront la session.
    # -----------------------------------------------------

    input(
        "Si nécessaire, connectez-vous à EFMS, "
        "puis appuyez sur Entrée ici..."
    )

    page.goto(URL)

    page.wait_for_timeout(5000)

    # Chercher l'iframe global_chart.php
    frame = None

    for f in page.frames:

        if "global_chart.php" in f.url:
            frame = f
            break

    if frame is None:
        print("ERREUR : iframe global_chart.php introuvable.")
        context.close()
        exit()

    print("Graphique trouvé :")
    print(frame.url)

    # Attendre Highcharts
    frame.wait_for_function(
        """
        () => (
            window.Highcharts &&
            Highcharts.charts &&
            Highcharts.charts.some(c => c)
        )
        """
    )

    # Lecture directe des séries Highcharts
    series = frame.evaluate(
        """
        () => {

            const chart = Highcharts.charts.find(c => c);

            return chart.series.map(s => {

                const points = s.points
                    .filter(p => p.y !== null);

                const lastPoint =
                    points.length
                    ? points[points.length - 1]
                    : null;

                return {
                    name: s.name,
                    value: lastPoint ? lastPoint.y : null,
                    timestamp: lastPoint ? lastPoint.x : null
                };
            });
        }
        """
    )

    # Afficher toutes les séries Grid intéressantes
    results = []

    for s in series:

        name = s["name"]

        is_voltage = (
            "Voltage L1 - N (GRID)" in name
            or "Voltage L2 - N (GRID)" in name
            or "Voltage L3 - N (GRID)" in name
        )

        is_current = (
            "Curent L1 (GRID)" in name
            or "Curent L2 (GRID)" in name
            or "Curent L3 (GRID)" in name
        )

        if is_voltage or is_current:

            timestamp = None

            if s["timestamp"] is not None:

                timestamp = datetime.fromtimestamp(
                    s["timestamp"] / 1000
                )

            results.append({
                "Parameter": name,
                "Value": s["value"],
                "Date": timestamp
            })

    df = pd.DataFrame(results)

    print("\nRESULTATS :")
    print(df.to_string(index=False))

    df.to_excel(
        "test_EFMS_ABG004.xlsx",
        index=False
    )

    print(
        "\nFichier créé : test_EFMS_ABG004.xlsx"
    )

    context.close()