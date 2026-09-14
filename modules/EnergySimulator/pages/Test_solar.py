from models.solar import SolarModel

solar = SolarModel(

    daily_energy_kwh=32,

    sunrise=6,

    sunset=18

)

solar.reset()

for step in range(288):

    solar.step(step)

print(solar.dataframe())

print()

print(solar.summary())