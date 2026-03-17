"""Peristaltic pump example driver based on gpiod + TCA9555."""

import time

import gpiod

from lib.TCA9555 import TCA9555


SUBDIVISION = 800
PUL_CHIP = "/dev/gpiochip1"
PUL_LINE = 1
DIR_PIN = 11
ENA_PIN = 10

DIRECTION = 1
RPM = 300
REVOLUTIONS = 10
SECOND = 3


class PeriPump:
    def __init__(
        self,
        tca9555_instance: TCA9555,
        pul_chip=PUL_CHIP,
        pul_line=PUL_LINE,
        dir_pin=DIR_PIN,
        ena_pin=ENA_PIN,
    ):
        if tca9555_instance is None:
            raise ValueError("tca9555_instance is required")

        self.pul_chip = pul_chip
        self.pul_line = pul_line
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin

        self.tca9555 = tca9555_instance
        self._subdivision = SUBDIVISION
        self._rpm = RPM
        self._direction = DIRECTION

        self.chip_pul = None
        self.line_pul = None
        self.set_pin_config()

    def enable(self):
        self.tca9555.write(self.ena_pin, False)

    def disable(self):
        self.tca9555.write(self.ena_pin, True)

    def pulse(self):
        pulse_interval = 30.0 / (self._rpm * self._subdivision)
        self.line_pul.set_value(1)
        time.sleep(pulse_interval)
        self.line_pul.set_value(0)
        time.sleep(pulse_interval)

    def run(self, revolutions=None):
        revs = revolutions if revolutions is not None else REVOLUTIONS
        total_pulses = int(revs * self._subdivision)

        self.enable()
        try:
            for _ in range(total_pulses):
                self.pulse()
        finally:
            self.disable()

    def run_by_time(self, seconds=None):
        run_time = seconds if seconds is not None else SECOND
        pulses_per_second = self._rpm * self._subdivision / 60.0
        total_pulses = int(run_time * pulses_per_second)
        start_time = time.time()

        self.enable()
        try:
            for _ in range(total_pulses):
                self.pulse()
                if (time.time() - start_time) >= run_time:
                    break
        finally:
            self.disable()

    def set_pin_config(self, pul_chip=None, pul_line=None, dir_pin=None, ena_pin=None):
        if pul_chip is not None:
            self.pul_chip = pul_chip
        if pul_line is not None:
            self.pul_line = pul_line
        if dir_pin is not None:
            self.dir_pin = dir_pin
        if ena_pin is not None:
            self.ena_pin = ena_pin

        if self.line_pul is not None:
            try:
                self.line_pul.release()
            except Exception:
                pass
        if self.chip_pul is not None:
            try:
                self.chip_pul.close()
            except Exception:
                pass

        self.chip_pul = gpiod.Chip(self.pul_chip)
        self.line_pul = self.chip_pul.get_line(self.pul_line)
        self.line_pul.request(consumer="peri_pump", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        self.tca9555.set_mode([self.dir_pin, self.ena_pin], "output")

    def cleanup(self):
        try:
            self.disable()
        finally:
            if self.line_pul is not None:
                try:
                    self.line_pul.release()
                except Exception:
                    pass
                self.line_pul = None
            if self.chip_pul is not None:
                try:
                    self.chip_pul.close()
                except Exception:
                    pass
                self.chip_pul = None

    def subdivision(self, subdiv_value):
        self._subdivision = int(subdiv_value)

    def direction(self, direction):
        if direction not in (0, 1):
            raise ValueError("direction must be 0 or 1")
        self.tca9555.write(self.dir_pin, bool(direction))
        self._direction = direction

    def rpm(self, rpm_value):
        self._rpm = rpm_value
