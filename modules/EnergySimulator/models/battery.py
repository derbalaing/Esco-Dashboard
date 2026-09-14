"""
battery.py
----------------------------------------
Battery model for Telecom Hybrid System

Author : ChatGPT + Mohamed Derbala

Simulation step : 5 minutes

Supported technologies

- Lithium
- ACID (OPzV, OPzS, Shoto...)

"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


# =====================================================
# Battery State
# =====================================================

@dataclass
class BatteryState:

    time: float

    soc: float

    voltage: float

    current: float

    power: float

    energy: float

    mode: str


# =====================================================
# Battery Class
# =====================================================

class Battery:

    def __init__(

        self,
        battery_type="Lithium",
        nb_battery=4,
        capacity_ah=100,
        nominal_voltage=48,
        efficiency=95,
        dod=80,
        soc_initial=80,
        soc_start_charge=50,
        soc_stop_charge=95,
        k1=0.20,
        k2=0.05,
        dt=5,

        generator_start_soc=50,

        generator_stop_soc=95,
        battery_quality=100,
    ):

        #################################################

        self.type = battery_type

        self.nb = nb_battery

        self.capacity = capacity_ah

        self.total_capacity_theoretical = self.nb * self.capacity

        self.battery_quality = battery_quality

        if self.battery_quality < 0:
            self.battery_quality = 0

        if self.battery_quality > 100:
            self.battery_quality = 100

        self.total_capacity = (
            self.total_capacity_theoretical
            * self.battery_quality
            / 100
        )

        # Qualité batterie entre 0 et 100 %
        self.battery_quality = battery_quality

        # Sécurité
        if self.battery_quality < 0:
            self.battery_quality = 0

        if self.battery_quality > 100:
            self.battery_quality = 100

        # Capacité réelle en Ah
        self.total_capacity = (
            self.total_capacity_theoretical
            * self.battery_quality
            / 100
        )

        self.nominal_voltage = nominal_voltage

        self.efficiency = efficiency / 100

        self.dod = dod

        self.dt = dt

        self.generator_start_soc = generator_start_soc
        self.generator_stop_soc = generator_stop_soc

        #################################################

        self.soc = soc_initial

        self.soc_start_charge = soc_start_charge
        self.soc_stop_charge = soc_stop_charge

        self.k1 = k1

        self.k2 = k2

        #################################################

        self.energy_nominal = (

            self.total_capacity

            * self.nominal_voltage

        )

        #################################################

        self.history = []
    #####################################################

    def reset(self):
        """
        Remise à zéro de la batterie avant chaque simulation.
        """

        self.soc = getattr(self, "soc_initial", self.soc)

        if hasattr(self, "voltage_from_soc"):
            self.voltage = self.voltage_from_soc()
        else:
            self.voltage = getattr(self, "nominal_voltage", 48)

        self.current = 0
        self.power = 0

        if hasattr(self, "total_capacity"):
            self.energy = self.total_capacity * self.voltage * self.soc / 100
        else:
            self.energy = 0

        self.history = []





    def voltage_from_soc(self):

        """
        Voltage according to SOC
        """

        if self.type == "Lithium":

            soc_points = np.array(

                [0,10,20,30,40,50,60,70,80,90,95,100]

            )

            voltage_points = np.array(

                [46.5,
                 47.2,
                 48.0,
                 49.0,
                 49.9,
                 50.8,
                 51.5,
                 52.2,
                 52.8,
                 53.3,
                 53.6,
                 54.0]

            )

        else:

            soc_points = np.array(

                [0,10,20,30,40,50,60,70,80,90,95,100]

            )

            voltage_points = np.array(

                [44.5,
                 45.5,
                 46.2,
                 46.9,
                 47.8,
                 48.8,
                 49.8,
                 50.8,
                 51.8,
                 52.7,
                 53.2,
                 54.0]

            )

        return np.interp(

            self.soc,

            soc_points,

            voltage_points

        )
    

        #####################################################

    def energy(self):

        """
        Remaining energy
        """

        return (

            self.energy_nominal

            * self.soc

            / 100

        )
    
        #####################################################

    def max_charge_current(self):


        total_capacity = self.total_capacity

        if self.type.lower() == "lithium":

            if self.soc >= 100:
                return 0

        return total_capacity * self.k1


        #################################################

        # ACID


        if self.soc <= self.soc_start_charge:
            return total_capacity * self.k1

        if self.soc >= self.soc_stop_charge:
            return 0

        ratio = (
            self.soc_stop_charge - self.soc
        ) / (
            self.soc_stop_charge - self.soc_start_charge
        )

        return total_capacity * (
            self.k2 + ratio * (self.k1 - self.k2)
        )

        #################################################

        ratio = (95 - self.soc) / 45

        current = (

            self.capacity * self.nb

            * (

                self.k2

                +

                ratio

                * (self.k1 - self.k2)

            )

        )

        return current
    
        #####################################################

    def save_state(

        self,

        time,

        current,

        power,

        mode

    ):

        self.history.append(

            BatteryState(

                time=time,

                soc=self.soc,

                voltage=self.voltage_from_soc(),

                current=current,

                power=power,

                energy=self.energy(),

                mode=mode

            )

        )

            #####################################################

    def discharge(self, load_power):

        """
        Décharge de la batterie

        load_power : puissance de la charge (W)

        Retour :
            courant batterie (A)
        """

        voltage = self.voltage_from_soc()

        current = load_power / voltage

        power = current * voltage

        # Energie fournie pendant dt

        energy_out = power * self.dt / 60

        delta_soc = (

            energy_out

            / self.energy_nominal

            / self.efficiency

            * 100

        )

        self.soc -= delta_soc

        #################################################

        min_soc = 100 - self.dod

        if self.soc < min_soc:

            self.soc = min_soc

        #################################################

        return current, power
    

        #####################################################

    def charge_lithium(self):

        """
        Charge Lithium

        Courant constant
        """

        voltage = self.voltage_from_soc()

        total_capacity = self.total_capacity

        current = total_capacity * self.k1

        power = current * voltage

        energy_in = power * self.dt / 60

        delta_soc = (

            energy_in

            * self.efficiency

            / self.energy_nominal

            * 100

        )

        self.soc += delta_soc

        if self.soc > 100:

            self.soc = 100

        return current, power
    
        #####################################################

    def charge_acid(self):

        """
        Charge batterie ACID

        Courant variable
        """

        voltage = self.voltage_from_soc()

        current = self.max_charge_current()

        power = current * voltage

        energy_in = power * self.dt / 60

        delta_soc = (

            energy_in

            * self.efficiency

            / self.energy_nominal

            * 100

        )

        self.soc += delta_soc

        if self.soc > self.soc_stop_charge:
            self.soc = self.soc_stop_charge

        return current, power
    
    #####################################################

    def charge(self):

        """
        Choix automatique du modèle
        """

        if self.type == "Lithium":

            return self.charge_lithium()

        else:

            return self.charge_acid()
        


    #####################################################

    def step(

        self,

        mode,

        load_power=0,

        time=0

    ):

        """
        mode

        charge

        discharge
        """

        if mode == "charge":

            current, power = self.charge()

        elif mode == "discharge":

            current, power = self.discharge(load_power)

            current = -current

            power = -power

        else:

            current = 0

            power = 0

        self.save_state(

            time,

            current,

            power,

            mode

        )


          #####################################################

    def dataframe(self):

        """
        Historique
        """

        return pd.DataFrame(

            [

                vars(x)

                for x in self.history

            ]

        )


        #####################################################

    def simulate(
        self,
        mode,
        duration_hours,
        load_power=2000
    ):
        """
        Simulation complète

        mode : "charge" ou "discharge"

        duration_hours : durée de simulation

        load_power : puissance load en décharge
        """

        self.history = []

        n_steps = int(duration_hours * 60 / self.dt)

        for step in range(n_steps):

            time = step * self.dt / 60

            if mode == "charge":

                self.step(
                    mode="charge",
                    time=time
                )

                min_soc = 100 - self.dod

                if self.soc <= min_soc:
                    self.soc = min_soc
                    break

            else:

                self.step(
                    mode="discharge",
                    load_power=load_power,
                    time=time
                )

                min_soc = 100 - self.dod

                if self.soc <= min_soc:

                    self.soc = min_soc

                    break

        return self.dataframe() 



    #####################################################

    def summary(self):

        df = self.dataframe()

        if len(df) == 0:
            return {}

        return {

            "SOC Initial":df.iloc[0]["soc"],

            "SOC Final":df.iloc[-1]["soc"],

            "Voltage Final":df.iloc[-1]["voltage"],

            "Current Final":df.iloc[-1]["current"],

            "Energy Final":df.iloc[-1]["energy"],

            "Simulation Time":df.iloc[-1]["time"],

            "Battery Quality (%)": self.battery_quality,
            "Theoretical Capacity (Ah)": self.total_capacity_theoretical,
            "Real Capacity (Ah)": self.total_capacity,
            "Theoretical Energy (kWh)": round(
                self.total_capacity_theoretical * self.nominal_voltage / 1000,
                3,
            ),
            "Real Energy (kWh)": round(
                self.energy_nominal / 1000,
                3,
            ),


        }
    
    def need_generator(self):

        """
        Retourne True si le GE doit démarrer.
        """

        return self.soc <= self.generator_start_soc
    
    def generator_can_stop(self):

        """
        Retourne True si le GE peut être arrêté.
        """

        if self.type.lower() == "lithium":

            return self.soc >= self.generator_stop_soc

        else:

            return (

                self.soc >= self.generator_stop_soc

                or

                abs(self.current) <= self.stop_current()
            )
        
        def stop_current(self):

            """
            Courant de fin de charge.
            """

            return self.total_capacity / 5
        



        @property
        def charge_power(self):

            return max(0, self.current * self.voltage)
        
        @property
        def discharge_power(self):

            return max(0, -self.current * self.voltage)
        

        def max_charge_power(self):
            """
            Puissance maximale de charge (W)
            """
            return self.max_charge_current() * self.voltage
        
        def max_discharge_power(self):
            """
            Puissance maximale de décharge (W)
            """
            return self.max_discharge_current() * self.voltage
        


# =====================================================
# Compatibility Patch for EnergyManager / EnergyFlow
# Add this block at the END of battery.py
# =====================================================

def _battery_stop_current(self):
    return self.total_capacity / 5


def _battery_max_discharge_current(self):
    min_soc = 100 - self.dod

    if self.soc <= min_soc:
        return 0

    return self.total_capacity


def _battery_max_charge_power(self):
    if self.type.lower() != "lithium":
        if self.soc >= self.soc_stop_charge:
            return 0

    if self.type.lower() == "lithium":
        if self.soc >= 100:
            return 0

    voltage = self.voltage_from_soc()

    return max(0, self.max_charge_current() * voltage)


def _battery_max_discharge_power(self):
    voltage = self.voltage_from_soc()

    return max(0, self.max_discharge_current() * voltage)


def _battery_generator_can_stop(self):
    if self.type.lower() == "lithium":
        return self.soc >= self.generator_stop_soc

    return (
        self.soc >= self.generator_stop_soc
        or (
            hasattr(self, "current")
            and self.current > 0
            and abs(self.current) <= self.stop_current()
            and self.soc >= self.generator_stop_soc - 5
        )
    )


def _battery_step_compatible(
    self,
    mode=None,
    load_power=0,
    time=0,
    charge_power=None,
    discharge_power=None,
):
    voltage = self.voltage_from_soc()

    if charge_power is None and discharge_power is None:

        if mode == "charge":
            charge_power = self.max_charge_power()
            discharge_power = 0

        elif mode == "discharge":
            charge_power = 0
            discharge_power = load_power

        else:
            charge_power = 0
            discharge_power = 0

    charge_power = max(0, charge_power or 0)
    discharge_power = max(0, discharge_power or 0)

    charge_power = min(charge_power, self.max_charge_power())
    discharge_power = min(discharge_power, self.max_discharge_power())

    energy_in = charge_power * self.dt / 60
    energy_out = discharge_power * self.dt / 60

    delta_soc_charge = 0
    delta_soc_discharge = 0

    if energy_in > 0:
        delta_soc_charge = (
            energy_in
            * self.efficiency
            / self.energy_nominal
            * 100
        )

    if energy_out > 0:
        delta_soc_discharge = (
            energy_out
            / self.efficiency
            / self.energy_nominal
            * 100
        )

    self.soc += delta_soc_charge
    self.soc -= delta_soc_discharge

    min_soc = 100 - self.dod

    if self.soc < min_soc:
        self.soc = min_soc

    if self.soc > 100:
        self.soc = 100

    if self.type.lower() != "lithium":
        if self.soc > self.soc_stop_charge:
            self.soc = self.soc_stop_charge

    net_power = charge_power - discharge_power

    if voltage > 0:
        current = net_power / voltage
    else:
        current = 0

    self.current = current
    self.power = net_power
    self.voltage = self.voltage_from_soc()

    if charge_power > 0 and discharge_power == 0:
        mode_result = "charge"
    elif discharge_power > 0 and charge_power == 0:
        mode_result = "discharge"
    elif charge_power > 0 and discharge_power > 0:
        mode_result = "mixed"
    else:
        mode_result = "idle"

    self.save_state(
        time=time,
        current=current,
        power=net_power,
        mode=mode_result,
    )


# Apply patch to Battery class
Battery.stop_current = _battery_stop_current
Battery.max_discharge_current = _battery_max_discharge_current
Battery.max_charge_power = _battery_max_charge_power
Battery.max_discharge_power = _battery_max_discharge_power
Battery.generator_can_stop = _battery_generator_can_stop
Battery.step = _battery_step_compatible




# =====================================================
# Patch: fix TypeError numpy.float64 object is not callable
# Add this block at the END of battery.py
# =====================================================

def _battery_energy_value(self):
    """
    Energie restante en Wh.
    """
    return self.energy_nominal * self.soc / 100


def _battery_reset_v2(self):
    """
    Reset batterie avant simulation.
    Supprime l'ancien attribut self.energy s'il existe.
    """

    if "energy" in self.__dict__:
        del self.__dict__["energy"]

    if not hasattr(self, "soc_initial"):
        self.soc_initial = self.soc

    self.soc = self.soc_initial
    self.voltage = self.voltage_from_soc()
    self.current = 0
    self.power = 0
    self.history = []


def _battery_save_state_v2(self, time, current, power, mode):
    """
    Sauvegarde robuste de l'état batterie.
    """

    if "energy" in self.__dict__:
        del self.__dict__["energy"]

    self.voltage = self.voltage_from_soc()
    self.current = current
    self.power = power

    energy_value = self.energy_nominal * self.soc / 100

    self.history.append(
        BatteryState(
            time=time,
            soc=self.soc,
            voltage=self.voltage,
            current=current,
            power=power,
            energy=energy_value,
            mode=mode,
        )
    )


# Apply patch
Battery.energy = _battery_energy_value
Battery.reset = _battery_reset_v2
Battery.save_state = _battery_save_state_v2


# =====================================================
# Patch ACID Charge Current Curve
# Courant fort au début puis décroissant progressivement
# =====================================================

def _battery_max_charge_current_v3(self):
    """
    Courant max de charge batterie.

    Lithium :
        courant constant = K1 × capacité réelle

    ACID :
        courant élevé au début,
        puis décroissant progressivement de K1 vers K2
        entre soc_start_charge et soc_stop_charge.
    """

    # Utiliser la capacité réelle, déjà corrigée par qualité batterie
    total_capacity = self.total_capacity

    # Sécurité : K1 doit être supérieur à K2
    k_start = max(self.k1, self.k2)
    k_end = min(self.k1, self.k2)

    # Lithium
    if self.type.lower() == "lithium":

        if self.soc >= 100:
            return 0

        return total_capacity * k_start

    # ACID
    if self.soc >= self.soc_stop_charge:
        return 0

    # Début de charge : courant maximum
    if self.soc <= self.soc_start_charge:
        return total_capacity * k_start

    # Zone de réduction progressive du courant
    ratio = (
        self.soc_stop_charge - self.soc
    ) / (
        self.soc_stop_charge - self.soc_start_charge
    )

    ratio = max(0, min(1, ratio))

    current = total_capacity * (
        k_end + ratio * (k_start - k_end)
    )

    return current


def _battery_max_charge_power_v3(self):
    """
    Puissance max de charge batterie en W.
    """
    voltage = self.voltage_from_soc()

    return max(
        0,
        self.max_charge_current() * voltage,
    )


# Apply patch
Battery.max_charge_current = _battery_max_charge_current_v3
Battery.max_charge_power = _battery_max_charge_power_v3