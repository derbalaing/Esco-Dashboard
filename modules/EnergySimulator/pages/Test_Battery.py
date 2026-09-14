from models.battery import Battery


battery = Battery(

    battery_type="Lithium",

    nb_battery=4,

    capacity_ah=100,

    soc_initial=80,

    charge_current=40  

)

df = battery.simulate(

    mode="discharge",

    duration_hours=8,

    load_power=2500

)

print(df)

print()

print(battery.summary())





import streamlit as st
from models.battery import Battery

st.title("🔋 Test Battery")

battery = Battery(
    battery_type="Lithium",
    nb_battery=4,
    capacity_ah=100,
    soc_initial=20,
    charge_current=40
)

df = battery.simulate(
    mode="charge",
    duration_hours=8,
    load_power=2500
)

st.subheader("Résumé")
st.write(battery.summary())

st.subheader("Historique")
st.dataframe(df)



import plotly.express as px

fig = px.line(
    df,
    x="time",
    y="soc",
    title="Évolution du SOC"
)

st.plotly_chart(fig, use_container_width=True)

fig = px.line(
    df,
    x="time",
    y="voltage",
    title="Tension Batterie"
)

st.plotly_chart(fig, use_container_width=True)

fig = px.line(
    df,
    x="time",
    y="current",
    title="Courant Batterie"
)

st.plotly_chart(fig, use_container_width=True)