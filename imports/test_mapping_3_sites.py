from pathlib import Path
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

IMPORTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = IMPORTS_DIR.parent

# IMPORTANT :
# On réutilise UN SEUL profil navigateur persistant.
# Cela évite de cloner la session via efms_state.json.
PROFILE_DIR = PROJECT_DIR / "efms_profile"

SITES_TEST = [
    "DAL019",
    "ABJ341",
    "MAN55",
]

BASE_LOCAL_CHART = (
    "https://efms-ivorycoast.camusat.com/"
    "local_chart.php?id=143"
)

START_URL = (
    BASE_LOCAL_CHART
    + "&sa_id=2093"
    + "&country=Ivory%20Coast"
    + "&radio_period=radio_period_07"
)

HOME_URL = "https://efms-ivorycoast.camusat.com/"

FILTER_HTML_FILE = IMPORTS_DIR / "EFMS_sites_filter_debug.html"


# ============================================================
# OUTILS
# ============================================================

def page_has_simultaneous_login(page):
    try:
        if "access_denied.php?mess=sim" in page.url:
            return True

        body = page.locator("body").inner_text(timeout=3000)

        return (
            "Simultaneous logins" in body
            or "Your session is terminated" in body
        )
    except Exception:
        return False


def page_needs_login(page):
    try:
        if page.locator('input[type="password"]').count() > 0:
            return True
    except Exception:
        pass

    text = ""

    try:
        text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        pass

    return (
        "log in" in text
        and "password" in text
    )


def get_chart_frame(page, timeout_ms=60000):
    """
    Retourne l'iframe #if_objects uniquement lorsque
    le formulaire EFMS est réellement chargé.
    """
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


def load_ivory_coast_site_filter(frame):
    print("\nChargement de la liste des sites Ivory Coast...")

    frame.evaluate(
        """
        () => {
            const country = document.getElementById('country');

            if (!country) {
                throw new Error('Select #country introuvable');
            }

            // Re-déclencher explicitement le onchange EFMS.
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
                (box.innerHTML || '').includes('chk_site_')
                ||
                box.querySelector('[id^="chk_site_"]') !== null
            );
        }
        """,
        timeout=120000
    )

    html = frame.locator("#td_1_2").inner_html()

    FILTER_HTML_FILE.write_text(
        html,
        encoding="utf-8"
    )

    print("Liste des sites chargée.")


def map_sites_from_filter(frame, target_sites):
    """
    Récupère les identifiants chk_site_<sa_id>
    correspondant aux codes sites recherchés.
    """
    return frame.evaluate(
        """
        (targets) => {
            const box = document.getElementById('td_1_2');

            if (!box) {
                throw new Error('#td_1_2 introuvable');
            }

            function clean(v) {
                return String(v || '')
                    .replace(/\\s+/g, ' ')
                    .trim();
            }

            const inputs = Array.from(
                box.querySelectorAll('[id^="chk_site_"]')
            );

            const candidates = inputs.map(el => {
                const texts = [];

                // label lié au checkbox
                try {
                    const label = box.querySelector(
                        `label[for="${CSS.escape(el.id)}"]`
                    );

                    if (label) {
                        texts.push(clean(label.innerText));
                    }
                } catch (e) {}

                // texte autour du checkbox
                let node = el;

                for (let level = 0; level < 6 && node; level++) {
                    node = node.parentElement;

                    if (!node) break;

                    const txt = clean(node.innerText);

                    if (txt && txt.length <= 1200) {
                        texts.push(txt);
                    }
                }

                texts.push(clean(el.value));
                texts.push(clean(el.name));
                texts.push(clean(el.getAttribute('title')));
                texts.push(clean(el.getAttribute('onclick')));

                return {
                    checkbox_id: el.id,
                    sa_id: el.id.replace(/^chk_site_/, ''),
                    context: clean(
                        texts.filter(Boolean).join(' | ')
                    )
                };
            });

            const results = {};

            for (const originalTarget of targets) {
                const target = String(originalTarget)
                    .trim()
                    .toUpperCase();

                const matches = candidates.filter(c =>
                    c.context.toUpperCase().includes(target)
                );

                if (matches.length > 0) {
                    const exactMatches = matches.filter(c => {
                        const words = c.context
                            .toUpperCase()
                            .split(/[^A-Z0-9_-]+/);

                        return words.includes(target);
                    });

                    const best = exactMatches.length
                        ? exactMatches[0]
                        : matches[0];

                    results[originalTarget] = {
                        found: true,
                        sa_id: best.sa_id,
                        checkbox_id: best.checkbox_id,
                        context: best.context,
                        match_count: matches.length
                    };

                    continue;
                }

                results[originalTarget] = {
                    found: false,
                    sa_id: null,
                    checkbox_id: null,
                    context: null,
                    match_count: 0
                };
            }

            return {
                checkbox_count: inputs.length,
                results: results
            };
        }
        """,
        target_sites
    )


def build_site_url(sa_id):
    return (
        BASE_LOCAL_CHART
        + f"&sa_id={sa_id}"
        + "&country=Ivory%20Coast"
        + "&radio_period=radio_period_07"
    )


def read_displayed_site(frame):
    try:
        link = frame.locator(
            'a[href*="sites.php"]'
        ).first

        if link.count() > 0:
            return link.inner_text().strip()
    except Exception:
        pass

    return ""


def ensure_authenticated(page):
    """
    Utilise le même profil persistant.
    Si la session a expiré, l'utilisateur se reconnecte
    manuellement DANS CE MEME navigateur.
    """

    page.goto(
        START_URL,
        wait_until="domcontentloaded",
        timeout=120000
    )

    page.wait_for_timeout(3000)

    # Cas session simultanée détectée par EFMS
    if page_has_simultaneous_login(page):
        print()
        print("=" * 72)
        print("EFMS a terminé la session pour connexion simultanée.")
        print("=" * 72)
        print()
        print("1. Fermez toutes les autres fenêtres/onglets EFMS.")
        print("2. Ne lancez PAS efms_login.py.")
        print("3. Dans CETTE fenêtre Playwright, nous allons nous reconnecter.")
        print()

        input(
            "Après avoir fermé les autres sessions EFMS, "
            "appuyez sur ENTREE ici..."
        )

        page.goto(
            HOME_URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        page.wait_for_timeout(2000)

    # Si login nécessaire, connexion manuelle dans le profil persistant
    if page_needs_login(page):
        print()
        print("Connexion EFMS nécessaire.")
        print(
            "Connectez-vous manuellement dans LA fenêtre "
            "qui vient de s'ouvrir."
        )
        print(
            "N'ouvrez pas EFMS dans un autre navigateur en parallèle."
        )

        input(
            "Quand vous êtes connecté au portail, "
            "revenez ici et appuyez sur ENTREE..."
        )

    # Revenir au graphique
    page.goto(
        START_URL,
        wait_until="domcontentloaded",
        timeout=120000
    )

    page.wait_for_timeout(3000)

    if page_has_simultaneous_login(page):
        return False

    frame = get_chart_frame(page)

    return frame is not None


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("=" * 72)
    print("EFMS - TEST MAPPING 3 SITES")
    print("MODE : UNE SEULE SESSION / PROFIL PERSISTANT")
    print("=" * 72)
    print("Sites :", ", ".join(SITES_TEST))
    print()
    print("Profil utilisé :")
    print(PROFILE_DIR)

    with sync_playwright() as p:

        # IMPORTANT :
        # launch_persistent_context = même profil navigateur à chaque run.
        # On n'utilise PAS efms_state.json.
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

            print("\n1 - Vérification de la session EFMS...")

            if not ensure_authenticated(page):
                print()
                print("ERREUR : EFMS refuse encore la session.")
                print(
                    "Vérifiez qu'aucune autre fenêtre EFMS "
                    "n'est ouverte avec ce compte."
                )
                return

            print("OK - session EFMS active.")

            frame = get_chart_frame(page)

            if frame is None:
                print("ERREUR : iframe graphique introuvable.")
                return

            print("\n2 - Lecture de la liste des sites...")

            load_ivory_coast_site_filter(frame)

            print("\n3 - Recherche des sa_id...")

            mapping_data = map_sites_from_filter(
                frame,
                SITES_TEST
            )

            print(
                "Nombre de checkbox sites détectées :",
                mapping_data["checkbox_count"]
            )

            mapping = mapping_data["results"]

            print("\n" + "-" * 72)

            all_ok = True

            for site in SITES_TEST:
                result = mapping.get(site, {})

                if result.get("found"):
                    print(
                        f"{site:<10} -> sa_id = "
                        f"{result['sa_id']}"
                    )
                else:
                    all_ok = False
                    print(
                        f"{site:<10} -> NON TROUVE"
                    )

            print("-" * 72)

            if not all_ok:
                print()
                print(
                    "Au moins un site n'a pas été trouvé."
                )
                print(
                    "Fichier debug créé :"
                )
                print(
                    FILTER_HTML_FILE.resolve()
                )
                return

            print(
                "\n4 - Vérification des 3 sites "
                "DANS LA MEME SESSION..."
            )

            for site in SITES_TEST:

                sa_id = mapping[site]["sa_id"]

                print(
                    f"\nOuverture {site} "
                    f"(sa_id={sa_id})..."
                )

                # Toujours la même page/context.
                page.goto(
                    build_site_url(sa_id),
                    wait_until="domcontentloaded",
                    timeout=120000
                )

                page.wait_for_timeout(2500)

                if page_has_simultaneous_login(page):
                    print(
                        "   ERREUR : EFMS a détecté "
                        "une connexion simultanée."
                    )
                    print(
                        "   Arrêt immédiat pour ne pas "
                        "terminer davantage la session."
                    )
                    return

                site_frame = get_chart_frame(page)

                if site_frame is None:
                    print(
                        "   ERREUR : graphique introuvable."
                    )
                    continue

                displayed = read_displayed_site(
                    site_frame
                )

                print(
                    "   Site affiché EFMS :",
                    displayed if displayed else "(non lu)"
                )

                if (
                    displayed
                    and site.upper() in displayed.upper()
                ):
                    print("   RESULTAT : OK")
                else:
                    print("   RESULTAT : A VERIFIER")

            print()
            print("=" * 72)
            print(
                "TEST TERMINE - UNE SEULE SESSION EFMS."
            )
            print("=" * 72)

        finally:
            context.close()


if __name__ == "__main__":
    main()