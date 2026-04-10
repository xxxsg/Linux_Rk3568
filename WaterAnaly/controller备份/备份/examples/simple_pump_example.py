#!/usr/bin/env python3
"""Simple PeriPump example using the current API only."""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def simple_example():
    from PeriPump import PeriPump
    from TCA9555 import TCA9555

    tca9555 = TCA9555()
    pump = PeriPump(tca9555)

    try:
        print("1. Forward single pulse")
        pump.direction(1)
        pump.enable()
        pump.pulse()
        pump.disable()

        print("2. Forward timed run")
        pump.direction(1)
        pump.run_by_time(3.0)

        print("3. Reverse continuous pulse loop")
        pump.direction(0)
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
    simple_example()
