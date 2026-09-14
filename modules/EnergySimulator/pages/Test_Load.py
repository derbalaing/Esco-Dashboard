from models.load import Load

load = Load(

    mode="profile",

    day_power=3000,

    night_power=2200

)

for t in range(288):

    load.step(t)

print(load.dataframe())

print(load.summary())