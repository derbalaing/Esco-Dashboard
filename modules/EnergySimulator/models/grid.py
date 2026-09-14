import numpy as np
import pandas as pd


class GridModel:

    ##############################################################

    def __init__(

            self,

            availability=80,

            outages=4,

            dt=5,

            seed=None

    ):

        self.availability = availability
        self.outages = max(0, outages)

        self.dt = dt
        self.dt_hour = dt / 60

        self.seed = seed

        if seed is not None:
            np.random.seed(seed)

        ############################################

        self.hour = 0

        self.available = True

        self.energy = 0

        self.schedule = None

        self.history = []

    ##############################################################

    def reset(self):

        self.hour = 0

        self.available = True

        self.energy = 0

        self.history = []

        self.schedule = self.generate_schedule()

    ##############################################################

    def generate_schedule(self):

        """
        Génère les coupures de la journée.
        Retourne un tableau de 288 états (1=ON, 0=OFF)
        """

        total_minutes = 24 * 60

        n_steps = int(total_minutes / self.dt)

        status = np.ones(n_steps, dtype=int)

        # Cas 2 : site off-grid
        if self.availability <= 0:
            return np.zeros(n_steps, dtype=int)

        # Cas 1 : Grid disponible 100 %
        if self.availability >= 100:
            return status



        # Cas incohérent : disponibilité entre 0 et 100 mais 0 coupure
        # On force au moins une coupure
        if self.outages <= 0:
            self.outages = 1
        ############################################

        total_outage = total_minutes * (100 - self.availability) / 100

        ############################################

        weights = np.random.rand(self.outages)

        weights /= weights.sum()

        durations = np.round(weights * total_outage)

        durations = durations.astype(int)

        diff = int(total_outage - durations.sum())

        durations[0] += diff

        ############################################

        occupied = np.zeros(n_steps, dtype=bool)

        for duration in durations:

            duration_steps = max(
                1,
                int(np.ceil(duration / self.dt))
            )

            placed = False

            attempts = 0

            while not placed:

                attempts += 1

                if attempts > 500:
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

        return status

    ##############################################################

    def step(self, step):

        if self.schedule is None:
            self.reset()

        # Heure absolue de simulation
        self.hour = step * self.dt_hour

        # On répète le planning Grid toutes les 24 h
        idx = step % len(self.schedule)

        self.available = bool(self.schedule[idx])

        self.history.append({
            "Hour": round(self.hour, 4),
            "Grid Available": int(self.available),
        })
    ##############################################################

    def dataframe(self):

        return pd.DataFrame(self.history)

    ##############################################################

    def summary(self):

        uptime = np.sum(self.schedule)

        total = len(self.schedule)

        return {

            "Availability (%)":
                round(100 * uptime / total, 2),

            "Outages":
                self.outages

        }