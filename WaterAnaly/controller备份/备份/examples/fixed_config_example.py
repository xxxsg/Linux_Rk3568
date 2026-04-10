#!/usr/bin/env python3
"""Fixed pin configuration example for the current PeriPump API."""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fixed_configuration_example():
    from PeriPump import PeriPump
    from TCA9555 import TCA9555

    tca9555 = TCA9555()
    pump = PeriPump(tca9555_instance=tca9555)

    try:
        pump.rpm(250)
        pump.subdivision(800)

        print("Forward 2 revolutions")
        pump.direction(1)
        pump.run(2.0)

        time.sleep(1)

        print("Reverse 1 revolution")
        pump.direction(0)
        pump.run(1.0)
    finally:
        pump.cleanup()
        tca9555.cleanup()


def emergency_stop_example():
    from PeriPump import PeriPump
    from TCA9555 import TCA9555

    tca9555 = TCA9555()
    pump = PeriPump(tca9555_instance=tca9555)

    try:
        pump.direction(1)
        pump.enable()
        try:
            while True:
                pump.pulse()
                time.sleep(0.001)
        except KeyboardInterrupt:
            pump.disable()
    finally:
        pump.cleanup()
        tca9555.cleanup()


if __name__ == "__main__":
    fixed_configuration_example()
