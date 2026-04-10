"""Peristaltic pump example based on the unified Pin/Stepper/Pump API."""

from lib import GpiodPin, Pump, Stepper, TCA9555, Tca9555Pin


TCA_BUS = 1
TCA_ADDR = 0x20

PUL_PIN = ("/dev/gpiochip1", 1)
DIR_PIN = 11
ENA_PIN = 10

STEPS_PER_REV = 800
RPM = 300


def main() -> None:
    io = TCA9555(i2c_bus=TCA_BUS, addr=TCA_ADDR)

    pul_pin = GpiodPin(PUL_PIN, consumer="pump_pul", mode="output")
    dir_pin = Tca9555Pin(io, DIR_PIN, mode="output")
    ena_pin = Tca9555Pin(io, ENA_PIN, mode="output")

    stepper = Stepper(
        pul_pin=pul_pin,
        dir_pin=dir_pin,
        ena_pin=ena_pin,
        steps_per_rev=STEPS_PER_REV,
    )
    stepper.set_dir_active_level(True)
    stepper.set_enable_active_level(True)
    stepper.set_auto_enable(True)
    stepper.set_rpm(RPM)

    pump = Pump(
        driver=stepper,
        dispense_direction="forward",
        aspirate_direction="reverse",
    )

    try:
        pump.dispense_revolutions(2.0)
        pump.aspirate_for_time(1.5)
    finally:
        pump.cleanup()
        io.close()


if __name__ == "__main__":
    main()
