import pandas as pd

from models.energy_flow import EnergyFlow
from models.simulation_config import SimulationConfig


class EnergyManager:
    """
    EMS principal du simulateur énergétique hybride télécom.

    Rôle :
    - lire Solar / Grid / Load ;
    - décider marche / arrêt GE ;
    - calculer les flux via EnergyFlow ;
    - mettre à jour Battery ;
    - mettre à jour Generator ;
    - enregistrer l'historique.
    """

    def __init__(
        self,
        solar,
        battery,
        grid,
        generator,
        load,
        config=None,
        simulation_hours=24,
        dt=5,
        ems_mode="Reliability",
    ):
        
        self.config = config or SimulationConfig(
            simulation_hours=simulation_hours,
            dt=dt,
            ems_mode=ems_mode,
        )

        self.config = config or SimulationConfig(
            simulation_hours=simulation_hours,
            dt=dt,
            ems_mode=ems_mode,
        )

        self.solar = solar
        self.battery = battery
        self.grid = grid
        self.generator = generator
        self.load = load

        self.flow = EnergyFlow()

        self.dt = self.config.dt
        self.dt_hour = self.config.dt_hour
        self.nb_steps = self.config.nb_steps

        self.generator_running = False

        self.history = []

        # Synchroniser les seuils GE avec la batterie
        if hasattr(self.battery, "generator_start_soc"):
            self.battery.generator_start_soc = self.config.generator_start_soc

        if hasattr(self.battery, "generator_stop_soc"):
            self.battery.generator_stop_soc = self.config.generator_stop_soc

    # ============================================================
    # INITIALISATION
    # ============================================================

    def initialize(self):

        self.history = []

        self.generator_running = False

        self.solar.reset()
        self.grid.reset()
        self.load.reset()
        self.battery.reset()
        self.generator.reset()
        self.flow.reset()

    def reset(self):

        self.initialize()

    # ============================================================
    # OUTILS GE
    # ============================================================

    def _is_generator_running(self):

        if hasattr(self.generator, "running"):
            return bool(self.generator.running)

        return self.generator_running

    def _start_generator(self):

        if hasattr(self.generator, "start"):
            self.generator.start()

        self.generator_running = True

    def _stop_generator(self):

        if hasattr(self.generator, "stop"):
            self.generator.stop()

        self.generator_running = False

    # ============================================================
    # DECISION EMS
    # ============================================================

    def _decide_generator(self):

        # Si le Grid est disponible, le GE est arrêté
        if self.grid.available:

            self._stop_generator()

            return

        # Si Grid absent et batterie basse => démarrage GE
        if not self._is_generator_running():

            if self.battery.need_generator():

                self._start_generator()

        # Si GE marche et batterie suffisamment rechargée => arrêt GE
        if self._is_generator_running():

            if self.battery.generator_can_stop():

                self._stop_generator()

    # ============================================================
    # UPDATE BATTERY
    # ============================================================

    def _update_battery(self, flows, hour):

        charge_power = (
            flows["solar_to_battery"]
            + flows["grid_to_battery"]
            + flows["generator_to_battery"]
        )

        discharge_power = flows["battery_to_load"]

        try:
            self.battery.step(
                charge_power=charge_power,
                discharge_power=discharge_power,
                time=hour,
            )

        except TypeError:
            # Compatibilité avec l'ancien modèle Battery
            if discharge_power > 0:

                self.battery.step(
                    mode="discharge",
                    load_power=discharge_power,
                    time=hour,
                )

            elif charge_power > 0:

                self.battery.step(
                    mode="charge",
                    time=hour,
                )

            else:

                if hasattr(self.battery, "save_state"):
                    self.battery.save_state(
                        time=hour,
                        current=0,
                        power=0,
                        mode="idle",
                    )

    # ============================================================
    # UPDATE GENERATOR
    # ============================================================

    def _update_generator(self, flows, hour):

        voltage = getattr(
            self.battery,
            "voltage",
            self.battery.voltage_from_soc(),
        )

        load_power = flows["generator_to_load"]

        battery_charge_power = flows["generator_to_battery"]

        if self._is_generator_running():

            try:
                self.generator.step(
                    load_power=load_power,
                    battery_charge_power=battery_charge_power,
                    voltage=voltage,
                    time=hour,
                )

            except TypeError:
                required_power = load_power + battery_charge_power

                self.generator.step(
                    required_power=required_power,
                    voltage=voltage,
                    time=hour,
                )

        else:

            try:
                self.generator.step(
                    load_power=0,
                    battery_charge_power=0,
                    voltage=voltage,
                    time=hour,
                )

            except TypeError:
                pass

    # ============================================================
    # UN PAS DE SIMULATION
    # ============================================================

    def step(self, step):

        # 1. Mise à jour des composants passifs
        self.solar.step(step)
        self.grid.step(step)
        self.load.step(step)

        hour = getattr(
            self.solar,
            "hour",
            step * self.dt_hour,
        )

        # 2. Décision marche / arrêt GE
        self._decide_generator()

        # 3. Calcul des flux
        allow_grid_charge = (
            self.config.ems_mode.lower() == "reliability"
        )

        flows = self.flow.calculate(
            solar_power=self.solar.power,
            load_power=self.load.power,
            grid_available=self.grid.available,
            generator_running=self._is_generator_running(),
            battery=self.battery,
            generator=self.generator,
            allow_grid_charge=allow_grid_charge,
        )



                # Sécurité : vérifier si le load est réellement alimenté
        served_load = (
            flows.get("solar_to_load", 0)
            + flows.get("grid_to_load", 0)
            + flows.get("battery_to_load", 0)
            + flows.get("generator_to_load", 0)
        )

        missing_load = max(
            0,
            self.load.power - served_load,
        )

        flows["unserved_load"] = max(
            flows.get("unserved_load", 0),
            missing_load,
        )

        # Si site off-grid, GE OFF et load non servi,
        # alors le GE doit démarrer immédiatement.
        if (
            not self.grid.available
            and not self._is_generator_running()
            and missing_load > 1
        ):

            self._start_generator()

            flows = self.flow.calculate(
                solar_power=self.solar.power,
                load_power=self.load.power,
                grid_available=self.grid.available,
                generator_running=self._is_generator_running(),
                battery=self.battery,
                generator=self.generator,
                allow_grid_charge=allow_grid_charge,
            )



        # 4. Mise à jour batterie
        self._update_battery(
            flows=flows,
            hour=hour,
        )

        # 5. Mise à jour GE
        self._update_generator(
            flows=flows,
            hour=hour,
        )

        # 6. Historique global
        self.update_history(
            flows=flows,
            hour=hour,
        )

    # ============================================================
    # HISTORIQUE
    # ============================================================

    def update_history(self, flows, hour):

        row = {
            "Hour": hour,

            "EMS Mode": self.config.ems_mode,

            "Grid Available": int(self.grid.available),

            "Generator Running": int(self._is_generator_running()),

            "Solar Power (W)": self.solar.power,

            "Load Power (W)": self.load.power,

            "Battery SOC (%)": self.battery.soc,

            "Battery Voltage (V)": getattr(
                self.battery,
                "voltage",
                self.battery.voltage_from_soc(),
            ),

            "Battery Current (A)": getattr(
                self.battery,
                "current",
                0,
            ),

            "Battery Power (W)": getattr(
                self.battery,
                "power",
                0,
            ),

            "Generator Power (W)": getattr(
                self.generator,
                "power",
                0,
            ),

            "Generator Fuel Total (L)": getattr(
                self.generator,
                "fuel",
                0,
            ),

            "Generator Running Hours": getattr(
                self.generator,
                "running_hours",
                0,
            ),

            "Generator Starts": getattr(
                self.generator,
                "start_counter",
                0,
            ),

            **flows,
        }

        # Energies par pas en Wh
        for key in [
            "solar_to_load",
            "solar_to_battery",
            "solar_lost",
            "grid_to_load",
            "grid_to_battery",
            "battery_to_load",
            "generator_to_load",
            "generator_to_battery",
            "unserved_load",
        ]:

            value = row.get(key, 0)

            row[key] = value

            row[key + "_Wh"] = value * self.dt_hour

        self.history.append(row)

    # ============================================================
    # RUN COMPLET
    # ============================================================

    def run(self):

        # Recalcul sécurisé du nombre de pas
        self.dt = self.config.dt
        self.dt_hour = self.dt / 60
        self.nb_steps = int(self.config.simulation_hours * 60 / self.dt)

        self.initialize()

        for step in range(self.nb_steps):
            self.step(step)

        return self.dataframe()

    # ============================================================
    # DATAFRAME
    # ============================================================

    def dataframe(self):

        return pd.DataFrame(self.history)

    # ============================================================
    # KPI
    # ============================================================

    def summary(self):

        df = self.dataframe()

        if df.empty:
            return {}

        def kwh(col):

            if col not in df.columns:
                return 0

            return df[col].sum() / 1000

        grid_energy = (
            kwh("grid_to_load_Wh")
            + kwh("grid_to_battery_Wh")
        )

        generator_energy = (
            kwh("generator_to_load_Wh")
            + kwh("generator_to_battery_Wh")
        )

        solar_energy = getattr(
            self.solar,
            "energy",
            kwh("solar_to_load_Wh")
            + kwh("solar_to_battery_Wh")
            + kwh("solar_lost_Wh"),
        ) / 1000

        load_energy = getattr(
            self.load,
            "energy",
            kwh("solar_to_load_Wh")
            + kwh("grid_to_load_Wh")
            + kwh("battery_to_load_Wh")
            + kwh("generator_to_load_Wh"),
        ) / 1000

        return {
            "Simulation Hours": self.config.simulation_hours,

            "Time Step (min)": self.config.dt,

            "Solar Production (kWh)": round(solar_energy, 3),

            "Load Energy (kWh)": round(load_energy, 3),

            "Grid Energy (kWh)": round(grid_energy, 3),

            "Battery Discharge (kWh)": round(
                kwh("battery_to_load_Wh"),
                3,
            ),

            "Generator Energy (kWh)": round(
                generator_energy,
                3,
            ),

            "Solar Lost (kWh)": round(
                kwh("solar_lost_Wh"),
                3,
            ),

            "Unserved Load (kWh)": round(
                kwh("unserved_load_Wh"),
                3,
            ),

            "Fuel Consumption (L)": round(
                getattr(self.generator, "fuel", 0),
                3,
            ),

            "Generator Running Hours": round(
                getattr(self.generator, "running_hours", 0),
                3,
            ),

            "Generator Starts": getattr(
                self.generator,
                "start_counter",
                0,
            ),

            "SOC Min (%)": round(
                df["Battery SOC (%)"].min(),
                2,
            ),

            "SOC Max (%)": round(
                df["Battery SOC (%)"].max(),
                2,
            ),

            "SOC Final (%)": round(
                df["Battery SOC (%)"].iloc[-1],
                2,
            ),

            "Grid Availability (%)": round(
                df["Grid Available"].mean() * 100,
                2,
            ),
        }