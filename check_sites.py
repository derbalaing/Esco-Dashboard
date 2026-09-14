# check_sites.py

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

query = """
SELECT
    s.site_id,
    s.code_site,
    s.site_name,
    s.typologie_fms,
    s.remote_name,
    t.team_name
FROM sites s
LEFT JOIN teams t
    ON s.team_id = t.team_id
ORDER BY s.code_site
"""

df = pd.read_sql(query, engine)

print(df.head(50))
print(f"\nNombre total de sites : {len(df)}")