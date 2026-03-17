"""MAX31865 RTD temperature sensor driver."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from lib.SoftSPI import SoftSPI


MAX31865_DEFAULT_RREF = 430.0
MAX31865_DEFAULT_R0 = 100.0
MAX31865_DEFAULT_WIRES = 2
MAX31865_DEFAULT_FILTER_FREQUENCY = 60

MAX31865_CONFIG_REG = 0x00
MAX31865_RTD_MSB_REG = 0x01
MAX31865_RTD_LSB_REG = 0x02
MAX31865_HIGH_FAULT_MSB_REG = 0x03
MAX31865_HIGH_FAULT_LSB_REG = 0x04
MAX31865_LOW_FAULT_MSB_REG = 0x05
MAX31865_LOW_FAULT_LSB_REG = 0x06
MAX31865_FAULT_STATUS_REG = 0x07

MAX31865_CONFIG_BIAS = 0x80
MAX31865_CONFIG_MODE_AUTO = 0x40
MAX31865_CONFIG_1SHOT = 0x20
MAX31865_CONFIG_3WIRE = 0x10
MAX31865_CONFIG_FAULT_DETECT_MASK = 0x0C
MAX31865_CONFIG_FAULT_CLEAR = 0x02
MAX31865_CONFIG_FILTER_50HZ = 0x01

MAX31865_FAULT_HIGH_THRESHOLD = 0x80
MAX31865_FAULT_LOW_THRESHOLD = 0x40
MAX31865_FAULT_REFIN_LOW = 0x20
MAX31865_FAULT_REFIN_HIGH = 0x10
MAX31865_FAULT_RTDIN_LOW = 0x08
MAX31865_FAULT_OVUV = 0x04

MAX31865_RTD_A = 3.9083e-3
MAX31865_RTD_B = -5.775e-7


class MAX31865:
    """MAX31865 驱动。"""

    @staticmethod
    def convert_adc_to_resistance(raw_adc: int, rref: float = MAX31865_DEFAULT_RREF) -> float:
        adc_value = int(raw_adc) & 0x7FFF
        return adc_value * float(rref) / 32768.0

    @staticmethod
    def convert_resistance_to_temperature(resistance: float, r0: float = MAX31865_DEFAULT_R0) -> float:
        resistance = float(resistance)
        r0 = float(r0)

        if resistance <= 0 or r0 <= 0:
            raise ValueError("resistance and r0 must be greater than 0")

        if resistance >= r0:
            discriminant = (MAX31865_RTD_A * MAX31865_RTD_A) - (4.0 * MAX31865_RTD_B * (1.0 - (resistance / r0)))
            if discriminant < 0:
                raise ValueError("invalid resistance, discriminant is negative")
            return (-MAX31865_RTD_A + math.sqrt(discriminant)) / (2.0 * MAX31865_RTD_B)

        ratio = resistance / r0 * 100.0
        return (
            -242.02
            + 2.2228 * ratio
            + 2.5859e-3 * math.pow(ratio, 2)
            - 4.8260e-6 * math.pow(ratio, 3)
            - 2.8183e-8 * math.pow(ratio, 4)
            + 1.5243e-10 * math.pow(ratio, 5)
        )

    @classmethod
    def convert_adc_to_temperature(
        cls,
        raw_adc: int,
        rref: float = MAX31865_DEFAULT_RREF,
        r0: float = MAX31865_DEFAULT_R0,
    ) -> float:
        resistance = cls.convert_adc_to_resistance(raw_adc, rref)
        return cls.convert_resistance_to_temperature(resistance, r0)

    def __init__(
        self,
        spi: "SoftSPI",
        rref: float = MAX31865_DEFAULT_RREF,
        r0: float = MAX31865_DEFAULT_R0,
        wires: int = MAX31865_DEFAULT_WIRES,
        filter_frequency: int = MAX31865_DEFAULT_FILTER_FREQUENCY,
    ) -> None:
        """初始化 MAX31865。"""
        if spi is None:
            raise ValueError("spi instance is required")
        if wires not in (2, 3, 4):
            raise ValueError("wires must be 2, 3, or 4")
        if filter_frequency not in (50, 60):
            raise ValueError("filter_frequency must be 50 or 60")

        self.spi = spi
        self.rref = float(rref)
        self.r0 = float(r0)
        self.wires = wires
        self.filter_frequency = filter_frequency
        self._closed = False

        self._configure()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("MAX31865 device is closed")

    def _configure(self) -> None:
        config = MAX31865_CONFIG_BIAS
        if self.wires == 3:
            config |= MAX31865_CONFIG_3WIRE
        if self.filter_frequency == 50:
            config |= MAX31865_CONFIG_FILTER_50HZ
        self.write_register(MAX31865_CONFIG_REG, config)
        self.clear_faults()

    def _read_u8(self, reg_addr: int) -> int:
        self._ensure_open()
        self.spi.cs_low()
        try:
            rx_data = self.spi.transfer([reg_addr & 0x7F, 0x00])
            return rx_data[1]
        finally:
            self.spi.cs_high()

    def _read_many(self, reg_addr: int, length: int) -> List[int]:
        self._ensure_open()
        if length <= 0:
            return []

        self.spi.cs_low()
        try:
            rx_data = self.spi.transfer([reg_addr & 0x7F] + ([0x00] * length))
            return rx_data[1:]
        finally:
            self.spi.cs_high()

    def _write_u8(self, reg_addr: int, value: int) -> None:
        self._ensure_open()
        self.spi.cs_low()
        try:
            self.spi.transfer([(reg_addr | 0x80) & 0xFF, value & 0xFF])
        finally:
            self.spi.cs_high()

    def _read_rtd(self) -> int:
        msb, lsb = self._read_many(MAX31865_RTD_MSB_REG, 2)
        return ((msb << 8) | lsb) >> 1

    @property
    def raw_rtd(self) -> int:
        return self._read_rtd()

    @property
    def resistance(self) -> float:
        return self.adc_to_resistance(self.raw_rtd)

    @property
    def temperature(self) -> float:
        return self.resistance_to_temperature(self.resistance)

    @property
    def fault_status(self) -> int:
        return self._read_u8(MAX31865_FAULT_STATUS_REG)

    def read_fault(self) -> int:
        return self.fault_status

    def clear_faults(self) -> None:
        config = self._read_u8(MAX31865_CONFIG_REG)
        self._write_u8(MAX31865_CONFIG_REG, config | MAX31865_CONFIG_FAULT_CLEAR)

    def read_register(self, reg_addr: int) -> int:
        return self._read_u8(reg_addr)

    def read_registers(self, reg_addr: int, length: int) -> List[int]:
        return self._read_many(reg_addr, length)

    def write_register(self, reg_addr: int, value: int) -> None:
        self._write_u8(reg_addr, value)

    def write_registers(self, reg_addr: int, values: List[int]) -> None:
        self._ensure_open()
        if not isinstance(values, list):
            raise TypeError("values must be a list of int")

        self.spi.cs_low()
        try:
            self.spi.transfer([(reg_addr | 0x80) & 0xFF] + [value & 0xFF for value in values])
        finally:
            self.spi.cs_high()

    def adc_to_resistance(self, raw_adc: int) -> float:
        return self.convert_adc_to_resistance(raw_adc, self.rref)

    def resistance_to_temperature(self, resistance: float) -> float:
        return self.convert_resistance_to_temperature(resistance, self.r0)

    def calculate_temperature(self, raw_adc: int) -> float:
        return self.convert_adc_to_temperature(raw_adc, self.rref, self.r0)

    def close(self) -> None:
        if self._closed:
            return
        self.spi.close()
        self._closed = True

    def __enter__(self) -> "MAX31865":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
