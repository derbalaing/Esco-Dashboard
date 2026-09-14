# from models.solar import Solar
from models.battery import Battery
# from models.grid import Grid
from models.generator import Generator
from models.load import Load
from models.energy_manager import EnergyManager



battery = Battery(
    battery_type="Lithium",
    nb_battery=4,
    capacity_ah=100,
    soc_initial=80
)



generator = Generator(
    rated_power_kw=15000,
    fuel_curve=[2.5, 3.5, 5.0]
)

load = Load(
    average_power=2500
)

ems = EnergyManager(

  #  solar=solar,

    battery=battery,

   # grid=grid,

    generator=generator,

    load=load,

    dt=5

)

ems.initialize()

ems.step(0)

print(ems.history)