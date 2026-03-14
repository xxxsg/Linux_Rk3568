"""Hardware layer based on CircuitPython drivers."""

from dataclasses import dataclass
import time
from typing import Any, Dict, Optional

import board
import busio
import digitalio

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_max31865
import adafruit_tca9555

import config as cfg
from config import *


def _get_board_pin(pin_name: str):
    try:
        return getattr(board, pin_name)
    except AttributeError as exc:
        raise ValueError(f"board pin not found: {pin_name!r}") from exc


class TCA9555Driver:
    def __init__(self, i2c, addr):
        self.chip = adafruit_tca9555.TCA9555(i2c, address=addr)
        self._pins: Dict[int, Any] = {}
        self.state = 0x0000

    def _get_pin(self, pin_no):
        if pin_no not in self._pins:
            pin = self.chip.get_pin(pin_no)
            pin.switch_to_output(value=False)
            self._pins[pin_no] = pin
        return self._pins[pin_no]

    def write_pin(self, pin_no, high):
        pin = self._get_pin(pin_no)
        pin.value = bool(high)
        if high:
            self.state |= 1 << pin_no
        else:
            self.state &= ~(1 << pin_no)


class ADS1115Driver:
    _CHANNEL_MAP = {
        0: ADS.P0,
        1: ADS.P1,
        2: ADS.P2,
        3: ADS.P3,
    }

    def __init__(self, i2c, addr):
        self.ads = ADS.ADS1115(i2c, address=addr)
        self.ads.gain = 1
        self._channels = {
            idx: AnalogIn(self.ads, channel)
            for idx, channel in self._CHANNEL_MAP.items()
        }

    def read_channel_mv(self, channel):
        if channel not in self._channels:
            raise ValueError(f"unsupported ADS1115 channel: {channel}")
        return self._channels[channel].voltage * 1000.0


class MAX31865Driver:
    def __init__(
        self,
        spi,
        cs_pin_name: str,
        *,
        wires: int = 2,
        rtd_nominal: float = 100.0,
        ref_resistor: float = 430.0,
    ):
        self.cs = digitalio.DigitalInOut(_get_board_pin(cs_pin_name))
        self.sensor = adafruit_max31865.MAX31865(
            spi,
            self.cs,
            wires=wires,
            rtd_nominal=rtd_nominal,
            ref_resistor=ref_resistor,
        )

    def read_temperature(self):
        return self.sensor.temperature

    def deinit(self):
        self.cs.deinit()


class ValveCtrl:
    def __init__(self, tca_driver, valve_pin_map):
        self.tca = tca_driver
        self.valve_pin_map = valve_pin_map

    def open(self, valve_names):
        names = valve_names if isinstance(valve_names, list) else [valve_names]
        for name in names:
            self.tca.write_pin(self.valve_pin_map[name], True)

    def close(self, valve_names):
        names = valve_names if isinstance(valve_names, list) else [valve_names]
        for name in names:
            self.tca.write_pin(self.valve_pin_map[name], False)

    def close_all(self):
        for _, pin in self.valve_pin_map.items():
            self.tca.write_pin(pin, False)


class StepperPump:
    """PUL/DIR/ENA pump wrapper for external stepper driver."""

    def __init__(self, tca_driver, pul_pin, dir_pin, ena_pin, subdivision, rpm):
        self.tca = tca_driver
        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin
        self.subdivision = subdivision
        self.rpm = rpm
        self.half_period = 30.0 / (self.rpm * self.subdivision)
        self.direction = DIR_FORWARD

        self.tca.write_pin(self.pul_pin, False)
        self.tca.write_pin(self.dir_pin, False)
        self.tca.write_pin(self.ena_pin, True)

    def set_direction(self, direction):
        if direction not in (DIR_FORWARD, DIR_REVERSE):
            raise ValueError(f"unsupported pump direction: {direction}")
        self.direction = direction
        self.tca.write_pin(self.dir_pin, direction == DIR_FORWARD)

    def enable(self):
        self.tca.write_pin(self.ena_pin, False)

    def disable(self):
        self.tca.write_pin(self.ena_pin, True)

    def pulse(self):
        self.tca.write_pin(self.pul_pin, True)
        time.sleep(self.half_period)
        self.tca.write_pin(self.pul_pin, False)
        time.sleep(self.half_period)

    def run_for(self, duration_ms):
        end_at = time.time() + duration_ms / 1000.0
        while time.time() < end_at:
            self.pulse()


class MeterOptics:
    def __init__(self, ads_driver):
        self.ads = ads_driver

    def read_upper_transmittance(self):
        return self.ads.read_channel_mv(METER_UPPER_CHANNEL)

    def read_lower_transmittance(self):
        return self.ads.read_channel_mv(METER_LOWER_CHANNEL)


class DigestOptics:
    def __init__(self, ads_driver):
        self.ads = ads_driver

    def read_absorbance(self):
        return self.ads.read_channel_mv(DIGEST_OPTICS_CHANNEL)


class TempController:
    def __init__(self, sensor_driver):
        self.sensor = sensor_driver
        self.target_temp = 0.0

    def start(self, target_temp):
        self.target_temp = target_temp

    def read_temperature(self):
        return self.sensor.read_temperature()

    def hold(self, hold_ms):
        time.sleep(hold_ms / 1000.0)

    def stop(self):
        self.target_temp = 0.0


@dataclass
class HardwareContext:
    bus: Any
    valve: ValveCtrl
    pump: StepperPump
    meter_optics: MeterOptics
    temp_ctrl: TempController
    digest_optics: DigestOptics
    spi: Optional[Any] = None
    temp_sensor: Optional[MAX31865Driver] = None

    def shutdown(self):
        self.pump.disable()
        self.valve.close_all()
        if self.temp_sensor is not None:
            self.temp_sensor.deinit()
        if self.spi is not None and hasattr(self.spi, "deinit"):
            self.spi.deinit()
        if self.bus is not None and hasattr(self.bus, "deinit"):
            self.bus.deinit()


def create_hardware_context():
    """Create and return hardware context."""
    i2c = busio.I2C(board.SCL, board.SDA)
    tca = TCA9555Driver(i2c, TCA9555_I2C_ADDR)
    ads = ADS1115Driver(i2c, ADS1115_I2C_ADDR)

    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    temp_sensor = MAX31865Driver(
        spi,
        getattr(cfg, "MAX31865_CS_PIN", "D5"),
        wires=getattr(cfg, "MAX31865_WIRES", 2),
        rtd_nominal=getattr(cfg, "MAX31865_RTD_NOMINAL", 100.0),
        ref_resistor=getattr(cfg, "MAX31865_REF_RESISTOR", 430.0),
    )

    return HardwareContext(
        bus=i2c,
        valve=ValveCtrl(tca, VALVE_PIN_MAP),
        pump=StepperPump(
            tca,
            pul_pin=PUMP_PUL_PIN,
            dir_pin=PUMP_DIR_PIN,
            ena_pin=PUMP_ENA_PIN,
            subdivision=PUMP_SUBDIVISION,
            rpm=PUMP_TARGET_RPM,
        ),
        meter_optics=MeterOptics(ads),
        temp_ctrl=TempController(temp_sensor),
        digest_optics=DigestOptics(ads),
        spi=spi,
        temp_sensor=temp_sensor,
    )
