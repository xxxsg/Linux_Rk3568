"""蠕动泵最小示例。"""

from __future__ import annotations

from lib.pins import GpiodPin, Tca9555Pin
from lib.pump import Pump
from lib.stepper import Stepper
from lib.TCA9555 import TCA9555


def main():
    tca9555 = TCA9555(i2c_bus=1, addr=0x20)

    pul = GpiodPin(("/dev/gpiochip1", 1), consumer="pump_pul", active_high=True, default_value=False)
    dir_pin = Tca9555Pin(tca9555, 11, active_high=True, initial_value=True)
    ena_pin = Tca9555Pin(tca9555, 10, active_high=True, initial_value=True)

    stepper = Stepper(
        pul_pin=pul,
        dir_pin=dir_pin,
        ena_pin=ena_pin,
        steps_per_revolution=800,
        rpm=300.0,
        default_revolutions=10.0,
        default_run_seconds=3.0,
    )
    pump = Pump(stepper)

    try:
        pump.dispense_revolutions(2.0)
        pump.aspirate_for_time(1.5)
    finally:
        pump.cleanup()
        tca9555.close()


if __name__ == "__main__":
    main()
