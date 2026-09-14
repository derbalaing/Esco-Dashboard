from pathlib import Path
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

IMPORTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = IMPORTS_DIR.parent

PROFILE_DIR = PROJECT_DIR / "efms_unique_profile"

SITES_TEST = [
    "DAL019",
    "ABJ341",
    "MAN055",
]

HOME_URL = "https://efms-ivorycoast.camusat.com/"

START_URL = (
    "https://efms-ivorycoast.camusat.com/"
    "local_chart.php?id=143&sa_id=2093"
    "&country=Ivory%20Coast"
    "&radio_period=radio_period_07"
)

DEBUG_HTML = IMPORTS_DIR / "EFMS_sites_filter_debug.html"


# ============================================================
# SESSION
# ============================================================

def simultaneous_login(page):
    try:
        if "access_denied.php" in page.url and "mess=sim" in page.url:
            return True

        text = page.locator("body").inner_text(timeout=3000)

        return (
            "Simultaneous logins" in text
            or "Your session is terminated" in text
        )
    except Exception:
        return False


def login_page(page):
    try:
        return page.locator('input[type="password"]').count() > 0
    except Exception:
        return False


# ============================================================
# IFRAME
# ============================================================

def get_chart_frame(page, timeout_ms=90000):
    iframe = page.locator("iframe#if_objects")

    try:
        iframe.wait_for(
            state="attached",
            timeout=timeout_ms
        )
    except Exception:
        return None

    for _ in range(max(1, timeout_ms // 500)):
        try:
            handle = iframe.element_handle()

            if handle is not None:
                frame = handle.content_frame()

                if frame is not None:
                    url = frame.url or ""

                    if (
                        "global_chart.php" in url
                        or "global_chart2.php" in url
                    ):
                        if (
                            frame.locator("form#search").count() > 0
                            and frame.locator("#country").count() > 0
                        ):
                            return frame
        except Exception:
            pass

        page.wait_for_timeout(500)

    return None


# ============================================================
# FILTRE / MAPPING
# ============================================================

def load_sites_filter(frame):
    """
    Charge la liste des sites Ivory Coast dans #td_1_2.
    """

    frame.evaluate(
        """
        () => {
            const country = document.getElementById('country');

            if (!country) {
                throw new Error('#country introuvable');
            }

            country.value = 'Ivory Coast';

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
            const box = document.getElementById('td_1_2');

            if (!box) return false;

            return (
                box.querySelector('[id^="chk_site_"]') !== null
                ||
                (box.innerHTML || '').includes('chk_site_')
            );
        }
        """,
        timeout=120000
    )

    # Laisser l'AJAX / SetCheckedItem terminer.
    frame.wait_for_timeout(1500)

    DEBUG_HTML.write_text(
        frame.locator("#td_1_2").inner_html(),
        encoding="utf-8"
    )


def map_sites(frame, targets):
    """
    La valeur du checkbox contient directement le code site :
    <input id="chk_site_3314" value="DAL019" ...>
    """

    return frame.evaluate(
        """
        (targets) => {
            const box = document.getElementById('td_1_2');

            if (!box) {
                throw new Error('#td_1_2 introuvable');
            }

            const checks = Array.from(
                box.querySelectorAll(
                    'input.client_checkboxes[id^="chk_site_"]'
                )
            );

            const results = {};

            for (const original of targets) {
                const target = String(original)
                    .trim()
                    .toUpperCase();

                const el = checks.find(
                    c =>
                        String(c.value || '')
                            .trim()
                            .toUpperCase()
                        === target
                );

                if (!el) {
                    results[original] = {
                        found: false,
                        sa_id: null,
                        checkbox_id: null
                    };
                    continue;
                }

                results[original] = {
                    found: true,
                    sa_id:
                        el.id.replace(
                            /^chk_site_/,
                            ''
                        ),
                    checkbox_id: el.id
                };
            }

            return {
                checkbox_count: checks.length,
                results
            };
        }
        """,
        targets
    )


# ============================================================
# CHANGEMENT SITE - POST DIRECT
# ============================================================

def prepare_site_post(frame, site_code, sa_id, checkbox_id):
    """
    IMPORTANT V4

    On n'appelle PLUS :
        CustomFilterSubmit()
        ClosePanels()
        Set_Chart_Site()

    On prépare directement le formulaire HTML :
      - tous les checkbox sites = unchecked
      - le site cible = checked
      - hidden #sa_id = sa_id cible

    Ainsi le POST contient une seule sélection site.
    """

    return frame.evaluate(
        """
        ({siteCode, saId, checkboxId}) => {

            const form =
                document.querySelector('form#search');

            if (!form) {
                throw new Error(
                    'form#search introuvable'
                );
            }

            const target =
                document.getElementById(
                    checkboxId
                );

            if (!target) {
                throw new Error(
                    'Checkbox introuvable : '
                    + checkboxId
                );
            }

            const hiddenSa =
                document.getElementById(
                    'sa_id'
                );

            if (!hiddenSa) {
                throw new Error(
                    '#sa_id introuvable'
                );
            }

            // 1. Décocher TOUS les sites.
            document
                .querySelectorAll(
                    'input.client_checkboxes'
                )
                .forEach(el => {
                    el.checked = false;
                    el.removeAttribute('checked');
                });

            // 2. Cocher UNIQUEMENT le site cible.
            target.checked = true;
            target.setAttribute(
                'checked',
                'checked'
            );

            // 3. Forcer également le sa_id cible.
            hiddenSa.value = String(saId);
            hiddenSa.setAttribute(
                'value',
                String(saId)
            );

            // 4. Vérifier ce que le formulaire enverra.
            const fd = new FormData(form);

            const selectedSites = [];

            for (const [name, value] of fd.entries()) {
                if (
                    String(name).startsWith(
                        'chk_site_'
                    )
                ) {
                    selectedSites.push({
                        name: String(name),
                        value: String(value)
                    });
                }
            }

            return {
                siteCode:
                    siteCode,

                sa_id:
                    hiddenSa.value,

                checkbox_id:
                    checkboxId,

                target_checked:
                    target.checked,

                selected_sites:
                    selectedSites,

                form_method:
                    form.method
            };
        }
        """,
        {
            "siteCode": site_code,
            "saId": sa_id,
            "checkboxId": checkbox_id,
        }
    )


def submit_search_form(frame):
    """
    Submit direct uniquement.

    Pas de CustomFilterSubmit(), donc pas de ClosePanels()
    et pas d'erreur hide_div(...).style pendant la navigation.
    """

    frame.locator(
        "form#search"
    ).evaluate(
        "(form) => form.submit()"
    )


def displayed_site(frame):
    try:
        link = frame.locator(
            'a[href*="sites.php"]'
        ).first

        if link.count() > 0:
            return link.inner_text().strip()

    except Exception:
        pass

    return ""


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("=" * 76)
    print("EFMS - TEST 3 SITES V4")
    print("UNE SESSION + POST DIRECT DU SITE")
    print("=" * 76)

    print(
        "Sites :",
        ", ".join(SITES_TEST)
    )

    print(
        "Profil :",
        PROFILE_DIR
    )

    with sync_playwright() as p:

        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={
                "width": 1800,
                "height": 1000
            }
        )

        try:
            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            # ------------------------------------------------
            # 1 - SESSION
            # ------------------------------------------------
            print("\n1 - Ouverture EFMS...")

            page.goto(
                HOME_URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            page.wait_for_timeout(2000)

            if simultaneous_login(page):
                print(
                    "ERREUR : session simultanée détectée."
                )
                return

            if login_page(page):

                print()
                print("Connexion nécessaire.")

                print(
                    "Connectez-vous manuellement "
                    "dans CETTE fenêtre uniquement."
                )

                input(
                    "Quand vous êtes connecté, "
                    "appuyez sur ENTREE ici..."
                )

            # ------------------------------------------------
            # 2 - CHART INITIAL
            # ------------------------------------------------
            print("\n2 - Ouverture du graphique EFMS...")

            page.goto(
                START_URL,
                wait_until="domcontentloaded",
                timeout=120000
            )

            page.wait_for_timeout(3000)

            if simultaneous_login(page):
                print(
                    "ERREUR : session simultanée détectée."
                )
                return

            frame = get_chart_frame(page)

            if frame is None:
                print(
                    "ERREUR : global_chart introuvable."
                )
                return

            print("OK - graphique chargé.")

            # ------------------------------------------------
            # 3 - MAPPING DES 3 SITES
            # ------------------------------------------------
            print(
                "\n3 - Chargement de la liste des sites..."
            )

            load_sites_filter(frame)

            mapping_data = map_sites(
                frame,
                SITES_TEST
            )

            mapping = mapping_data[
                "results"
            ]

            print(
                "Nombre de sites/checkbox détectés :",
                mapping_data[
                    "checkbox_count"
                ]
            )

            print()

            for site in SITES_TEST:

                r = mapping[site]

                if r["found"]:

                    print(
                        f"{site:<10} -> "
                        f"sa_id={r['sa_id']} "
                        f"({r['checkbox_id']})"
                    )

                else:

                    print(
                        f"{site:<10} -> "
                        "NON TROUVE"
                    )

            if not all(
                mapping[s]["found"]
                for s in SITES_TEST
            ):
                print(
                    "\nArrêt : au moins un "
                    "site est introuvable."
                )
                return

            # ------------------------------------------------
            # 4 - CHANGER SITE PAR POST DIRECT
            # ------------------------------------------------
            print()
            print(
                "4 - Changement des sites "
                "dans la même session..."
            )

            for site in SITES_TEST:

                # La page précédente a été rechargée :
                # reconstruire la liste site.
                load_sites_filter(frame)

                sa_id = (
                    mapping[site][
                        "sa_id"
                    ]
                )

                checkbox_id = (
                    mapping[site][
                        "checkbox_id"
                    ]
                )

                print()
                print(
                    f"Préparation {site} "
                    f"(sa_id={sa_id})..."
                )

                info = prepare_site_post(
                    frame,
                    site,
                    sa_id,
                    checkbox_id
                )

                print(
                    "   target_checked :",
                    info[
                        "target_checked"
                    ]
                )

                print(
                    "   sa_id envoyé   :",
                    info[
                        "sa_id"
                    ]
                )

                print(
                    "   sites cochés dans POST :",
                    info[
                        "selected_sites"
                    ]
                )

                # Sécurité :
                # une seule checkbox doit partir.
                selected = info[
                    "selected_sites"
                ]

                if (
                    len(selected) != 1
                    or
                    selected[0][
                        "name"
                    ]
                    != checkbox_id
                ):
                    print(
                        "   ERREUR : le POST "
                        "ne contient pas exactement "
                        "le site cible."
                    )
                    return

                print(
                    f"   Envoi de {site}..."
                )

                # Submit DIRECT.
                submit_search_form(
                    frame
                )

                # Attendre le reload du global_chart.
                page.wait_for_timeout(
                    7000
                )

                if simultaneous_login(page):
                    print(
                        "   ERREUR : connexion "
                        "simultanée détectée."
                    )
                    return

                frame = get_chart_frame(
                    page,
                    timeout_ms=120000
                )

                if frame is None:
                    print(
                        "   ERREUR : frame "
                        "introuvable après POST."
                    )
                    return

                shown = displayed_site(
                    frame
                )

                print(
                    "   Site affiché EFMS :",
                    shown
                    if shown
                    else "(non lu)"
                )

                if (
                    shown
                    and
                    site.upper()
                    in shown.upper()
                ):
                    print(
                        "   RESULTAT : OK"
                    )
                else:
                    print(
                        "   RESULTAT : ECHEC"
                    )
                    print(
                        "   Le serveur n'a pas "
                        "pris le site demandé."
                    )
                    return

            # ------------------------------------------------
            # FIN
            # ------------------------------------------------
            print()
            print("=" * 76)
            print(
                "SUCCES : LES 3 SITES ONT "
                "ETE CHANGES DANS UNE "
                "SEULE SESSION EFMS."
            )
            print("=" * 76)

        finally:
            context.close()


if __name__ == "__main__":
    main()