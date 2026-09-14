class EnergyFlow:

    ##############################################################


    """
    Calcul des flux instantanés d'énergie.

    Rôle :
    - ne démarre pas le GE ;
    - ne modifie pas le SOC ;
    - ne calcule pas le fuel ;
    - calcule seulement les flux de puissance en W.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.solar_to_load = 0
        self.solar_to_battery = 0
        self.solar_lost = 0

        self.grid_to_load = 0
        self.grid_to_battery = 0

        self.battery_to_load = 0

        self.generator_to_load = 0
        self.generator_to_battery = 0

        self.unserved_load = 0

    def calculate(
        self,
        solar_power,
        load_power,
        grid_available,
        generator_running,
        battery,
        generator,
        allow_grid_charge=True,
    ):

        self.reset()

        solar_power = max(0, float(solar_power))
        load_power = max(0, float(load_power))

        # =====================================================
        # 1. Solar -> Load
        # =====================================================

        self.solar_to_load = min(solar_power, load_power)

        remaining_load = load_power - self.solar_to_load
        remaining_solar = solar_power - self.solar_to_load

        # =====================================================
        # 2. Solar surplus -> Battery
        # =====================================================

        if remaining_solar > 0:

            max_charge = battery.max_charge_power()

            self.solar_to_battery = min(
                remaining_solar,
                max_charge,
            )

            remaining_solar -= self.solar_to_battery

        self.solar_lost = max(0, remaining_solar)

        # =====================================================
        # 3. GRID AVAILABLE
        # =====================================================

        if grid_available:

            self.grid_to_load = remaining_load
            remaining_load = 0

            if allow_grid_charge:

                available_charge = (
                    battery.max_charge_power()
                    - self.solar_to_battery
                )

                available_charge = max(0, available_charge)

                self.grid_to_battery = available_charge

        # =====================================================
        # 4. OFF-GRID / GRID NOT AVAILABLE
        # =====================================================

        else:

            if generator_running:

                # GE alimente le load
                self.generator_to_load = min(
                    remaining_load,
                    generator.rated_power,
                )

                remaining_load -= self.generator_to_load

                # GE recharge la batterie avec la puissance restante
                available_generator_power = (
                    generator.rated_power
                    - self.generator_to_load
                )

                available_generator_power = max(
                    0,
                    available_generator_power,
                )

                available_charge = (
                    battery.max_charge_power()
                    - self.solar_to_battery
                )

                available_charge = max(
                    0,
                    available_charge,
                )

                self.generator_to_battery = min(
                    available_generator_power,
                    available_charge,
                )

            else:

                # Batterie alimente le load
                max_discharge = battery.max_discharge_power()

                self.battery_to_load = min(
                    remaining_load,
                    max_discharge,
                )

                remaining_load -= self.battery_to_load

            # Ce qui reste n'est pas servi
            self.unserved_load = max(0, remaining_load)

        return self.as_dict()

    def as_dict(self):

        return {
            "solar_to_load": self.solar_to_load,
            "solar_to_battery": self.solar_to_battery,
            "solar_lost": self.solar_lost,

            "grid_to_load": self.grid_to_load,
            "grid_to_battery": self.grid_to_battery,

            "battery_to_load": self.battery_to_load,

            "generator_to_load": self.generator_to_load,
            "generator_to_battery": self.generator_to_battery,

            "unserved_load": self.unserved_load,
        }

    def summary(self):
        return self.as_dict()
    



    ##############################################################

    def summary(self):

        return {

            "Solar -> Load": self.solar_to_load,

            "Solar -> Battery": self.solar_to_battery,

            "Grid -> Load": self.grid_to_load,

            "Grid -> Battery": self.grid_to_battery,

            "Battery -> Load": self.battery_to_load,

            "Generator -> Load": self.generator_to_load,

            "Generator -> Battery": self.generator_to_battery,

            "Solar Lost": self.solar_lost

        }