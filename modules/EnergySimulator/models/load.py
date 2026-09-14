import pandas as pd
import numpy as np


class Load:

    ##############################################################

    def __init__(

            self,

            mode="constant",

            average_power=2500,

            day_power=3000,

            night_power=2200,

            day_start=7,

            night_start=23,

            profile=None,

            dt=5

    ):

        self.mode = mode

        self.average_power = average_power

        self.day_power = day_power
        self.night_power = night_power

        self.day_start = day_start
        self.night_start = night_start

        self.profile = profile

        self.dt = dt
        self.dt_hour = dt / 60

        self.power = average_power
        self.energy = 0

        self.history = []

    ##############################################################

    def reset(self):

        self.power = self.average_power
        self.energy = 0
        self.history = []

    ##############################################################

    def constant(self):

        return self.average_power

    ##############################################################

    def daily_profile(self, hour):

        if self.day_start <= hour < self.night_start:
            return self.day_power

        return self.night_power

    ##############################################################

    def custom_profile(self, step):

        if self.profile is None:
            return self.average_power

        if step < len(self.profile):
            return self.profile[step]

        return self.profile[-1]

    ##############################################################

    def step(self, time):

        ###############################################

        hour = time * self.dt_hour

        ###############################################

        if self.mode == "constant":

            self.power = self.constant()

        elif self.mode == "profile":

            self.power = self.daily_profile(hour)

        elif self.mode == "custom":

            self.power = self.custom_profile(time)

        else:

            self.power = self.average_power

        ###############################################

        energy_step = self.power * self.dt_hour

        self.energy += energy_step

        ###############################################

        self.history.append({

            "Time (h)": round(hour, 2),

            "Load Power (W)": self.power,

            "Energy Step (Wh)": energy_step,

            "Energy (Wh)": self.energy

        })

    ##############################################################

    def dataframe(self):

        return pd.DataFrame(self.history)

    ##############################################################

    def summary(self):

        return {

            "Average Load (W)": round(self.average_power, 1),

            "Total Energy (kWh)": round(self.energy / 1000, 2)

        }