import pandas as pd
import numpy as np


class Generator:

    def __init__(

        self,

        rated_power_kw=15,

        rated_voltage=53.5,

        efficiency=95,

        fuel_curve=None,

        dt=5

    ):
        
        if fuel_curve is None:

            self.fuel_curve = {

                0:0.8,

                7.5:2.6,

                13.2:3.3,

                19.8:3.9,

                26.4:4.7

            }

        else:

            self.fuel_curve = fuel_curve

        ###########################################

        self.rated_power = rated_power_kw * 1000

        self.rated_voltage = rated_voltage

        self.efficiency = efficiency / 100

        self.dt = dt

        self.dt_hour = dt / 60

        ###########################################

        self.reset()

    ################################################

    def reset(self):

        self.power = 0

        self.current = 0

        self.energy = 0

        self.fuel = 0

        self.fuel_rate = 0

        self.load_percent = 0

        self.running_hours = 0

        self.overload = False

        self.history = []

    ################################################


    def fuel_rate_from_load(self, load_percent):

        x = list(self.fuel_curve.keys())

        y = list(self.fuel_curve.values())

        return np.interp(

            load_percent,

            x,

            y

        )



    def _reset_step(self):

        self.power = 0

        self.current = 0

        self.load_percent = 0

        self.fuel_rate = 0

        self.overload = False


    def step(

        self,

        load_power,

        battery_charge_power,

        voltage,

        time

    ):


        self._reset_step()
        
        """
        required_power : puissance demandée (W)

        voltage : tension bus DC (V)

        """

        ###########################################

        self.overload = False

        ###########################################
        required_power = (

            load_power

            +

            battery_charge_power

        )
        if required_power <= 0:

            self.power = 0

            self.current = 0

            fuel_step = 0

        else:

            #######################################

            if required_power > self.rated_power:

                self.overload = True

                self.power = self.rated_power

            else:

                self.power = required_power

            #######################################
            if voltage <=0:

                voltage = self.rated_voltage
            self.current = self.power / voltage

            #######################################

            self.load_percent = (

                self.power

                /

                self.rated_power

            ) *100

            self.fuel_rate = self.fuel_rate_from_load(

                self.load_percent

            )
            fuel_step = self.fuel_rate * self.dt_hour

            #######################################

            self.running_hours += self.dt_hour

        ###########################################

        energy_step = self.power * self.dt_hour

        ###########################################

        self.energy += energy_step

        self.fuel += fuel_step

        ###########################################

        self.history.append(

            {

                "Time": time,

                "Power(W)": self.power,

                "Voltage(V)": voltage,

                "Current(A)": self.current,

                "Energy(Wh)": self.energy,

                "Fuel(L)": self.fuel,

                "Running(h)": self.running_hours,

                "Overload": self.overload,

                "Load(%)":self.load_percent,

                "Fuel Rate(L/h)":self.fuel_rate,

                "Fuel Step(L)":fuel_step,

                "Energy Step(Wh)":energy_step

            }

        )

    ################################################

    def dataframe(self):

        return pd.DataFrame(self.history)

    ################################################

@property

def running(self):

    return self.power >0

def summary(self):

    if self.fuel >0:

        efficiency = (

            self.energy/1000

        )/self.fuel

    else:

        efficiency = 0

    return {

        "Running Hours":

            round(self.running_hours,2),

        "Fuel (L)":

            round(self.fuel,2),

        "Energy (kWh)":

            round(self.energy/1000,2),

        "Average Load (%)":

            round(

                np.mean(

                    [

                        h["Load(%)"]

                        for h in self.history

                    ]

                ),

                1

            ),

        "Fuel Efficiency (kWh/L)":

            round(efficiency,2)

    }