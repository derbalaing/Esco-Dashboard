import streamlit as st
import plotly.express as px

from models.solar import SolarModel

st.title("☀️ Modèle Solaire")

pv = st.slider(
    "Puissance installée (kWc)",
    1.0,
    40.0,
    12.0,
)

eff = st.slider(
    "Rendement (%)",
    70,
    100,
    95,
)

solar = SolarModel(
    pv_kwc=pv,
    efficiency=eff / 100,
)

df = solar.daily_curve()

fig = px.line(
    df,
    x="Hour",
    y="PV_W",
    title="Production Photovoltaïque",
)

fig.update_layout(
    xaxis_title="Heure",
    yaxis_title="Puissance (W)",
)

st.plotly_chart(
    fig,
    use_container_width=True,
)

st.dataframe(df)



total_energy = df["PV_Wh"].sum() / 1000

st.metric(
    "Production solaire journalière",
    f"{total_energy:.2f} kWh"
)

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Puissance Max",
        f"{df['PV_W'].max()/1000:.2f} kW"
    )

with col2:
    st.metric(
        "Énergie journalière",
        f"{df['PV_Wh'].sum()/1000:.2f} kWh"
    )