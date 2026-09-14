# imports/import_teams.py

import pandas as pd


import sys
import os

# Ajoute la racine du projet au PYTHONPATH
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

from config.database import engine




df = pd.read_excel("data/Teams.xlsx")

df.columns = ["team_name"]

df.to_sql(
    "teams",
    engine,
    if_exists="append",
    index=False
)

print("Equipes importées")