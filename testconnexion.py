from config.database import engine

try:
    with engine.connect() as conn:
        print("Connexion Supabase OK")
except Exception as e:
    print(e)