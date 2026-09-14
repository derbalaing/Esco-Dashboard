from models.generator import Generator


fuel_curve = {

    0:0.7,

    2.5:1.1,

    5.0:1.8,

    7.5:2.6,

    10:3.4

}
ge = Generator(

    rated_power_kw=15,

    rated_voltage=53.5,

    efficiency=80

)

####################################################

for i in range(24):

    ge.step(

        load_power=3500,

        battery_charge_power=1800,

        voltage=53.5,

        time=i

    )

####################################################

print(ge.dataframe())

print()

