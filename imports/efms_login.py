from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "efms_state.json"

URL = "https://efms-ivorycoast.camusat.com/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            viewport={"width": 1600, "height": 900}
        )

        page = context.new_page()

        print("=" * 60)
        print("EFMS - Enregistrement de la session")
        print("=" * 60)

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        print()
        print("Connectez-vous normalement à EFMS dans le navigateur.")
        print("Quand vous êtes bien connecté et que le portail est affiché,")
        input("revenez ici et appuyez sur ENTREE... ")

        print()
        print("URL après connexion :")
        print(page.url)

        context.storage_state(path=str(STATE_FILE))

        print()
        print("Session EFMS enregistrée dans :")
        print(STATE_FILE)
        print()
        print("Vous pouvez maintenant lancer test_ABG004_juillet.py")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()