import numpy as np
import pandas as pd


class SolarModel:

    ##############################################################

    def __init__(

            self,

            daily_energy_kwh=30,

            sunrise=6.0,

            sunset=18.0,

            dt=5

    ):

        self.daily_energy_kwh = daily_energy_kwh

        self.sunrise = sunrise
        self.sunset = sunset

        self.dt = dt
        self.dt_hour = dt / 60

        ###########################################

        self.hour = 0

        self.power = 0

        self.energy = 0

        self.history = []

        ###########################################

        self.profile = None

    ##############################################################

    def reset(self):

        self.hour = 0

        self.power = 0

        self.energy = 0

        self.history = []

        self.profile = self.generate_profile()

    ##############################################################

    def generate_profile(self):

        """
        Génère un profil solaire de 24 h
        dont l'énergie totale est exactement
        daily_energy_kwh.
        """

        steps = int(24 * 60 / self.dt)

        hours = np.arange(steps) * self.dt_hour

        shape = []

        for h in hours:

            if h < self.sunrise or h > self.sunset:

                shape.append(0)

            else:

                x = (h - self.sunrise) / (self.sunset - self.sunrise)

                shape.append(np.sin(np.pi * x) ** 2)

        shape = np.array(shape)

        #############################################

        total_shape_energy = shape.sum() * self.dt_hour

        #############################################

        if total_shape_energy == 0:

            return np.zeros(steps)

        #############################################

        scale = (

            self.daily_energy_kwh * 1000

        ) / total_shape_energy

        #############################################

        return shape * scale

    ##############################################################

    def step(self, step):

        if self.profile is None:
            self.reset()

        # Heure absolue de simulation : 0 à 72 h par exemple
        self.hour = step * self.dt_hour

        # Index journalier : on répète le profil solaire toutes les 24 h
        idx = step % len(self.profile)

        self.power = self.profile[idx]

        energy_step = self.power * self.dt_hour

        self.energy += energy_step

        self.history.append({
            "Hour": round(self.hour, 4),
            "Solar Power (W)": self.power,
            "Energy Step (Wh)": energy_step,
            "Solar Energy (Wh)": self.energy,
        })

        #############################################

        self.history.append({

            "Hour": round(self.hour, 2),

            "Solar Power (W)": round(self.power, 1),

            "Energy Step (Wh)": round(energy_step, 2),

            "Solar Energy (Wh)": round(self.energy, 2)

        })

    ##############################################################

    def dataframe(self):

        return pd.DataFrame(self.history)

    ##############################################################

    def summary(self):

        return {

            "Daily Energy (kWh)":

                round(self.energy / 1000, 2),

            "Peak Power (W)":

                round(max(self.profile), 1)

        }