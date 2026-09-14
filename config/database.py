# config/database.py
import os

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

url = URL.create(
    drivername="postgresql+psycopg2",
    username="postgres.wotfaslpdzukfskmatxy",
    password="Sfax@@1985-*",
    host="aws-0-eu-west-1.pooler.supabase.com",
    port=5432,
    database="postgres"
)

engine = create_engine(
    url,
    connect_args={"sslmode": "require"}
)
