import numpy as np
import pandas as pd


class SolarModel:

    def __init__(
        self,
        pv_kwc,
        efficiency=0.95,
        sunrise=8.0,
        sunset=17.5,
    ):

        self.pv_kwc = pv_kwc
        self.efficiency = efficiency
        self.sunrise = sunrise
        self.sunset = sunset

    ###########################################################

    def power(self, hour):

        """
        hour : heure décimale
        retourne la puissance PV en W
        """

        if hour < self.sunrise or hour > self.sunset:
            return 0

        x = (hour - self.sunrise) / (self.sunset - self.sunrise)

        p = self.pv_kwc * 1000 * (np.sin(np.pi * x) ** 2)

        return p * self.efficiency

    ###########################################################

    def daily_curve(self):

        """
        Génère une journée avec un pas de 5 minutes
        """

        hours = []
        powers = []

        current = 0

        while current < 24 * 60:

            hour = current / 60

            hours.append(hour)

            powers.append(self.power(hour))

            current += 5

        return pd.DataFrame(
            {
                "Hour": hours,
                "PV_W": powers,
            }
        )
    
    ###########################################################

    def daily_curve(self):

        hours = []
        powers = []
        energies = []

        dt = 5 / 60      # 5 minutes en heure

        current = 0

        while current < 24 * 60:

            hour = current / 60

            power = self.power(hour)

            energy = power * dt      # Wh

            hours.append(hour)
            powers.append(power)
            energies.append(energy)

            current += 5

        df = pd.DataFrame({
            "Hour": hours,
            "PV_W": powers,
            "PV_Wh": energies
        })

        return df