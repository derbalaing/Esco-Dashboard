import numpy as np
import pandas as pd


class GridModel:

    def __init__(
        self,
        availability=80,
        outages=4,
        step=5,
        seed=None
    ):

        self.availability = availability
        self.outages = max(1, outages)
        self.step = step
        self.seed = seed

        if seed is not None:
            np.random.seed(seed)

    ####################################################################

    def daily_status(self):

        total_minutes = 24 * 60

        n_steps = total_minutes // self.step

        hours = np.arange(0, total_minutes, self.step) / 60

        # Etat du Grid (1 = ON)
        status = np.ones(n_steps, dtype=int)

        ###########################################################
        # Temps total de coupure
        ###########################################################

        total_outage = total_minutes * (100 - self.availability) / 100

        ###########################################################
        # Durée aléatoire de chaque coupure
        ###########################################################

        weights = np.random.rand(self.outages)

        weights = weights / weights.sum()

        durations = np.round(weights * total_outage)

        durations = durations.astype(int)

        ###########################################################
        # Ajustement pour respecter exactement le temps total
        ###########################################################

        diff = int(total_outage - durations.sum())

        durations[0] += diff

        ###########################################################
        # Placement aléatoire des coupures
        ###########################################################

        occupied = np.zeros(n_steps, dtype=bool)

        for duration in durations:

            duration_steps = max(1, int(np.ceil(duration / self.step)))

            placed = False

            attempt = 0

            while not placed:

                attempt += 1

                if attempt > 500:
                    break

                start = np.random.randint(
                    0,
                    n_steps - duration_steps
                )

                end = start + duration_steps

                if occupied[start:end].any():
                    continue

                occupied[start:end] = True

                status[start:end] = 0

                placed = True

        ###########################################################

        df = pd.DataFrame({

            "Hour": hours,

            "Grid": status

        })

        return df