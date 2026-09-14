from dataclasses import dataclass


@dataclass
class SimulationConfig:
    simulation_hours: float = 24
    dt: int = 5
    ems_mode: str = "Reliability"

    generator_start_soc: float = 50
    generator_stop_soc: float = 95

    @property
    def dt_hour(self):
        return self.dt / 60

    @property
    def nb_steps(self):
        return int(self.simulation_hours * 60 / self.dt)

    def summary(self):
        return {
            "Simulation Hours": self.simulation_hours,
            "Time Step (min)": self.dt,
            "EMS Mode": self.ems_mode,
            "GE Start SOC (%)": self.generator_start_soc,
            "GE Stop SOC (%)": self.generator_stop_soc,
        }