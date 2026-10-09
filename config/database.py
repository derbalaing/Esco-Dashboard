# config/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

try:
    import streamlit as st
except Exception:
    st = None


def get_secret(key, default=None):
    """
    Priorité :
    1. Streamlit secrets
    2. Variables d'environnement
    """
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass

        try:
            if "database" in st.secrets and key.lower() in st.secrets["database"]:
                return st.secrets["database"][key.lower()]
        except Exception:
            pass

    return os.getenv(key, default)


DB_HOST = get_secret("DB_HOST")
DB_NAME = get_secret("DB_NAME", "postgres")
DB_USER = get_secret("DB_USER")
DB_PASSWORD = get_secret("DB_PASSWORD")
DB_PORT = int(get_secret("DB_PORT", 5432))

if not DB_HOST or not DB_USER or not DB_PASSWORD:
    raise ValueError(
        "Configuration base de données manquante. "
        "Vérifiez DB_HOST, DB_USER, DB_PASSWORD dans Streamlit Secrets."
    )

url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME
)

engine = create_engine(
    url,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True
)
