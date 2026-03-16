"""MAX31865 RTD temperature sensor driver."""

from __future__ import annotations

import math


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
    """MAX31865 传感器驱动。"""

    @staticmethod
    def convert_adc_to_resistance(raw_adc: int, rref: float = MAX31865_DEFAULT_RREF) -> float:
        """将 MAX31865 原始 RTD ADC 值换算为 RTD 电阻值。"""
        adc_value = int(raw_adc) & 0x7FFF
        return adc_value * float(rref) / 32768.0

    @staticmethod
    def convert_resistance_to_temperature(
        resistance: float,
        r0: float = MAX31865_DEFAULT_R0,
    ) -> float:
        """将 RTD 电阻值换算为摄氏温度。"""
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
        """将 MAX31865 原始 RTD ADC 值直接换算为摄氏温度。"""
        resistance = cls.convert_adc_to_resistance(raw_adc, rref)
        return cls.convert_resistance_to_temperature(resistance, r0)

    def __init__(
        self,
        spi,
        rref: float = MAX31865_DEFAULT_RREF,
        r0: float = MAX31865_DEFAULT_R0,
        wires: int = MAX31865_DEFAULT_WIRES,
        filter_frequency: int = MAX31865_DEFAULT_FILTER_FREQUENCY,
    ):
        """初始化 MAX31865 设备。

        参数:
            spi: SPI 总线对象，需要提供 `cs_low()`、`cs_high()` 和 `transfer()`。
            rref: 参考电阻值，默认 430 欧姆。
            r0: RTD 在 0 摄氏度时的标称电阻，默认 100 欧姆。
            wires: RTD 接线方式，支持 2/3/4 线。
            filter_frequency: 工频滤波频率，支持 50 或 60Hz。
        """
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

    def _read_many(self, reg_addr: int, length: int) -> list[int]:
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
        """读取 RTD 原始 ADC 值。"""
        return self._read_rtd()

    @property
    def resistance(self) -> float:
        """读取当前 RTD 电阻值，单位为欧姆。"""
        return self.adc_to_resistance(self.raw_rtd)

    @property
    def temperature(self) -> float:
        """读取当前温度，单位为摄氏度。"""
        return self.resistance_to_temperature(self.resistance)

    @property
    def fault_status(self) -> int:
        """读取故障状态寄存器。"""
        return self._read_u8(MAX31865_FAULT_STATUS_REG)

    def read_fault(self) -> int:
        """读取当前故障状态码。"""
        return self.fault_status

    def clear_faults(self) -> None:
        """清除故障状态位。"""
        config = self._read_u8(MAX31865_CONFIG_REG)
        self._write_u8(MAX31865_CONFIG_REG, config | MAX31865_CONFIG_FAULT_CLEAR)

    def read_register(self, reg_addr: int) -> int:
        """读取单个寄存器。"""
        return self._read_u8(reg_addr)

    def read_registers(self, reg_addr: int, length: int) -> list[int]:
        """连续读取多个寄存器。"""
        return self._read_many(reg_addr, length)

    def write_register(self, reg_addr: int, value: int) -> None:
        """写入单个寄存器。"""
        self._write_u8(reg_addr, value)

    def write_registers(self, reg_addr: int, values: list[int]) -> None:
        """连续写入多个寄存器。"""
        self._ensure_open()
        if not isinstance(values, list):
            raise TypeError("values must be a list of int")

        self.spi.cs_low()
        try:
            self.spi.transfer([(reg_addr | 0x80) & 0xFF] + [value & 0xFF for value in values])
        finally:
            self.spi.cs_high()

    def adc_to_resistance(self, raw_adc: int) -> float:
        """按当前设备参数将原始 ADC 值换算为 RTD 电阻值。"""
        return self.convert_adc_to_resistance(raw_adc, self.rref)

    def resistance_to_temperature(self, resistance: float) -> float:
        """按当前设备参数将 RTD 电阻值换算为温度。"""
        return self.convert_resistance_to_temperature(resistance, self.r0)

    def calculate_temperature(self, raw_adc: int) -> float:
        """按当前设备参数将原始 ADC 值直接换算为温度。"""
        return self.convert_adc_to_temperature(raw_adc, self.rref, self.r0)

    def close(self) -> None:
        """关闭设备并释放底层 SPI 资源。"""
        if self._closed:
            return

        self.spi.close()
        self._closed = True

    def __enter__(self) -> "MAX31865":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


if __name__ == "__main__":
    print("MAX31865 基础计算示例")

    raw_adc = 9880
    resistance = MAX31865.convert_adc_to_resistance(raw_adc)
    temperature = MAX31865.convert_adc_to_temperature(raw_adc)

    print(f"raw_adc     : {raw_adc}")
    print(f"resistance  : {resistance:.4f} ohm")
    print(f"temperature : {temperature:.4f} C")

    print("")
    print("SoftSPI 使用示例:")
    print('spi = SoftSPI(sclk=("/dev/gpiochip0", 10), mosi=("/dev/gpiochip0", 11), miso=("/dev/gpiochip0", 12), cs=("/dev/gpiochip1", 5))')
    print("sensor = MAX31865(spi)")
    print("temperature = sensor.temperature")
