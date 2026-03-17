#!/usr/bin/env python3
"""Mixed IO example aligned with the current PeriPump API."""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def mixed_io_example():
    from PeriPump import PeriPump
    from TCA9555 import TCA9555

    tca9555 = TCA9555()
    pump = PeriPump(
        tca9555_instance=tca9555,
        pul_chip="/dev/gpiochip1",
        pul_line=1,
        dir_pin=11,
        ena_pin=12,
    )

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


def initialization_example():
    from PeriPump import PeriPump
    from TCA9555 import TCA9555

    tca9555 = TCA9555()
    pump = PeriPump(
        tca9555_instance=tca9555,
        pul_chip="/dev/gpiochip1",
        pul_line=1,
        dir_pin=11,
        ena_pin=12,
    )

    try:
        pump.rpm(200)
        pump.direction(1)
        pump.run_by_time(3.0)
    finally:
        pump.cleanup()
        tca9555.cleanup()


if __name__ == "__main__":
    mixed_io_example()
