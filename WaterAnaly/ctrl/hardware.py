"""Hardware adapters used by primitives/operations/recipe."""

from dataclasses import dataclass
import time

import board
import busio
import digitalio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_tca9555
import adafruit_max31865

from config import (
    ADS1115_I2C_ADDR,
    TCA9555_I2C_ADDR,
    VALVE_PIN_MAP,
    PUMP_PUL_PIN,
    PUMP_DIR_PIN,
    PUMP_ENA_PIN,
    PUMP_SUBDIVISION,
    PUMP_TARGET_RPM,
    MAX31865_CS_PIN,
    DIR_FORWARD,
)


class ValveCtrl:
    """TCA9555-based valve controller."""

    def __init__(self, tca, valve_pin_map):
        self.tca = tca
        self.valve_pin_map = valve_pin_map
        self._pin_cache = {}

    def _get_pin(self, pin_no):
        if pin_no not in self._pin_cache:
            pin = self.tca.get_pin(pin_no)
            pin.switch_to_output(value=False)
            self._pin_cache[pin_no] = pin
        return self._pin_cache[pin_no]

    def open(self, valve_names):
        names = valve_names if isinstance(valve_names, list) else [valve_names]
        for name in names:
            self._get_pin(self.valve_pin_map[name]).value = True

    def close(self, valve_names):
        names = valve_names if isinstance(valve_names, list) else [valve_names]
        for name in names:
            self._get_pin(self.valve_pin_map[name]).value = False

    def close_all(self):
        for name in self.valve_pin_map:
            self._get_pin(self.valve_pin_map[name]).value = False


class StepperPump:
    """Pump controller using TCA9555 pins: PUL, DIR, ENA."""

    def __init__(self, tca, pul_pin, dir_pin, ena_pin, subdivision, rpm):
        self.tca = tca
        self.pul_pin_no = pul_pin
        self.dir_pin_no = dir_pin
        self.ena_pin_no = ena_pin
        self.subdivision = subdivision
        self.rpm = rpm
        self._pin_cache = {}
        self._half_period = 30.0 / (self.rpm * self.subdivision)
        self._init_pins()

    def _get_pin(self, pin_no):
        if pin_no not in self._pin_cache:
            pin = self.tca.get_pin(pin_no)
            pin.switch_to_output(value=False)
            self._pin_cache[pin_no] = pin
        return self._pin_cache[pin_no]

    def _init_pins(self):
        self.pul_pin = self._get_pin(self.pul_pin_no)
        self.dir_pin = self._get_pin(self.dir_pin_no)
        self.ena_pin = self._get_pin(self.ena_pin_no)
        self.pul_pin.value = False
        self.dir_pin.value = False
        self.ena_pin.value = True

    def set_direction(self, direction):
        self.dir_pin.value = direction == DIR_FORWARD

    def enable(self):
        self.ena_pin.value = False

    def disable(self):
        self.ena_pin.value = True

    def pulse(self):
        self.pul_pin.value = True
        time.sleep(self._half_period)
        self.pul_pin.value = False
        time.sleep(self._half_period)

    def run_for(self, duration_ms):
        end_at = time.time() + duration_ms / 1000.0
        while time.time() < end_at:
            self.pulse()


class MeterOptics:
    """Reads upper/lower transmittance channels from ADS1115."""

    def __init__(self, ads):
        self.upper = AnalogIn(ads, ADS.P0)
        self.lower = AnalogIn(ads, ADS.P1)

    def read_upper_transmittance(self):
        return self.upper.voltage * 1000.0

    def read_lower_transmittance(self):
        return self.lower.voltage * 1000.0


class DigestOptics:
    """Reads digest absorbance from ADS1115 channel P2 by default."""

    def __init__(self, ads):
        self.channel = AnalogIn(ads, ADS.P2)

    def read_absorbance(self):
        return self.channel.voltage * 1000.0


class TempController:
    """MAX31865-based temperature controller (read + target hold logic)."""

    def __init__(self, cs_pin_name):
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        cs = digitalio.DigitalInOut(getattr(board, cs_pin_name))
        self.sensor = adafruit_max31865.MAX31865(spi, cs)
        self.target_temp = 0.0

    def start(self, target_temp):
        self.target_temp = target_temp

    def read_temperature(self):
        return self.sensor.temperature

    def hold(self, hold_ms):
        time.sleep(hold_ms / 1000.0)

    def stop(self):
        self.target_temp = 0.0


@dataclass
class HardwareContext:
    valve: ValveCtrl
    pump: StepperPump
    meter_optics: MeterOptics
    temp_ctrl: TempController
    digest_optics: DigestOptics

    def shutdown(self):
        self.pump.disable()
        self.valve.close_all()


def create_hardware_context():
    """Initialize all hardware adapters and return context."""
    i2c = busio.I2C(board.SCL, board.SDA)
    tca = adafruit_tca9555.TCA9555(i2c, address=TCA9555_I2C_ADDR)
    ads = ADS.ADS1115(i2c, address=ADS1115_I2C_ADDR)
    ads.gain = 1

    valve = ValveCtrl(tca, VALVE_PIN_MAP)
    pump = StepperPump(
        tca,
        pul_pin=PUMP_PUL_PIN,
        dir_pin=PUMP_DIR_PIN,
        ena_pin=PUMP_ENA_PIN,
        subdivision=PUMP_SUBDIVISION,
        rpm=PUMP_TARGET_RPM,
    )
    meter_optics = MeterOptics(ads)
    temp_ctrl = TempController(MAX31865_CS_PIN)
    digest_optics = DigestOptics(ads)

    return HardwareContext(
        valve=valve,
        pump=pump,
        meter_optics=meter_optics,
        temp_ctrl=temp_ctrl,
        digest_optics=digest_optics,
    )

