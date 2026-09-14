import pandas as pd


class EnergyFlow:

    def __init__(self):

        self.history = []

    #########################################################

    def calculate(

        self,

        solar_power,

        load_power,

        battery_charge_power,

        battery_discharge_power,

        grid_available,

        generator_available

    ):

        ###########################################

        solar_to_load = 0

        solar_to_battery = 0

        solar_lost = 0

        grid_to_load = 0

        grid_to_battery = 0

        battery_to_load = 0

        generator_to_load = 0

        generator_to_battery = 0

        mode = ""

        ####################################################

        if grid_available:

            mode = "GRID"

            ################################################

            solar_to_load = min(solar_power, load_power)

            remaining_load = load_power - solar_to_load

            remaining_solar = solar_power - solar_to_load

            ################################################

            if remaining_solar > 0:

                solar_to_battery = min(

                    remaining_solar,

                    battery_charge_power

                )

                solar_lost = remaining_solar - solar_to_battery

            ################################################

            if remaining_load > 0:

                grid_to_load = remaining_load

            ################################################

            if battery_charge_power > solar_to_battery:

                grid_to_battery = (

                    battery_charge_power

                    - solar_to_battery

                )

        ####################################################

        else:

            mode = "ISLANDED"

            ################################################

            solar_to_load = min(

                solar_power,

                load_power

            )

            remaining_load = load_power - solar_to_load

            remaining_solar = solar_power - solar_to_load

            ################################################

            if remaining_solar > 0:

                solar_to_battery = min(

                    remaining_solar,

                    battery_charge_power

                )

                solar_lost = (

                    remaining_solar

                    - solar_to_battery

                )

            ################################################

            if remaining_load > 0:

                battery_to_load = min(

                    battery_discharge_power,

                    remaining_load

                )

                remaining_load -= battery_to_load

            ################################################

            if remaining_load > 0 and generator_available:

                generator_to_load = remaining_load

                remaining_load = 0

                ################################################

                generator_to_battery = max(

                    0,

                    battery_charge_power

                    - solar_to_battery

                )

        ####################################################

        result = {

            "Mode": mode,

            "Solar->Load": solar_to_load,

            "Solar->Battery": solar_to_battery,

            "Solar Lost": solar_lost,

            "Grid->Load": grid_to_load,

            "Grid->Battery": grid_to_battery,

            "Battery->Load": battery_to_load,

            "Generator->Load": generator_to_load,

            "Generator->Battery": generator_to_battery

        }

        self.history.append(result)

        return result

    #########################################################

    def dataframe(self):

        return pd.DataFrame(self.history)

    #########################################################

    def reset(self):

        self.history = []