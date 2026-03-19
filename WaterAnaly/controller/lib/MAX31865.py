"""MAX31865 RTD 温度传感器驱动。"""

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
    """MAX31865 RTD 温度传感器驱动。

    支持原始 ADC、电阻值和温度值读取，也提供静态换算工具方法。
    """

    @staticmethod
    def convert_adc_to_resistance(raw_adc: int, rref: float = MAX31865_DEFAULT_RREF) -> float:
        """将 RTD 原始 ADC 值换算为电阻值。

        参数:
            raw_adc: 原始 ADC 值
            rref: 参考电阻阻值

        返回:
            float: 换算后的 RTD 电阻值
        """
        adc_value = int(raw_adc) & 0x7FFF
        return adc_value * float(rref) / 32768.0

    @staticmethod
    def convert_resistance_to_temperature(resistance: float, r0: float = MAX31865_DEFAULT_R0) -> float:
        """根据 PT100/PT1000 的 Callendar-Van Dusen 公式换算温度。

        参数:
            resistance: RTD 当前电阻值
            r0: RTD 在 0 摄氏度时的标称电阻

        返回:
            float: 摄氏温度
        """
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
        """将原始 ADC 值直接换算为摄氏温度。

        参数:
            raw_adc: 原始 ADC 值
            rref: 参考电阻阻值
            r0: RTD 在 0 摄氏度时的标称电阻

        返回:
            float: 摄氏温度
        """
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
        """初始化 MAX31865，并按线制与工频滤波参数完成配置。

        参数:
            spi: 底层 SoftSPI 对象
            rref: 参考电阻阻值
            r0: RTD 在 0 摄氏度时的标称电阻
            wires: RTD 线制，只能为 2、3、4
            filter_frequency: 工频滤波设置，只能为 50 或 60
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
        """确保设备尚未关闭。"""
        if self._closed:
            raise RuntimeError("MAX31865 device is closed")

    def _build_config_value(self) -> int:
        """生成配置寄存器默认值。"""
        config = MAX31865_CONFIG_BIAS
        if self.wires == 3:
            config |= MAX31865_CONFIG_3WIRE
        if self.filter_frequency == 50:
            config |= MAX31865_CONFIG_FILTER_50HZ
        return config

    def _spi_read(self, command: List[int]) -> List[int]:
        """执行一次 SPI 读事务。"""
        self._ensure_open()
        self.spi.cs_low()
        try:
            return self.spi.transfer(command)
        finally:
            self.spi.cs_high()

    def _spi_write(self, command: List[int]) -> None:
        """执行一次 SPI 写事务。"""
        self._ensure_open()
        self.spi.cs_low()
        try:
            self.spi.transfer(command)
        finally:
            self.spi.cs_high()

    def _configure(self) -> None:
        """写入基础配置，并清除历史故障标志。"""
        self.write_register(MAX31865_CONFIG_REG, self._build_config_value())
        self.clear_faults()

    def read_fault(self) -> int:
        """读取故障状态寄存器。"""
        return self.read_register(MAX31865_FAULT_STATUS_REG)

    def read_raw_rtd(self) -> int:
        """读取 RTD 原始 15 位 ADC 结果。"""
        data = self.read_registers(MAX31865_RTD_MSB_REG, 2)
        return ((data[0] << 8) | data[1]) >> 1

    def read_resistance(self) -> float:
        """读取 RTD 当前电阻值。"""
        raw_rtd = self.read_raw_rtd()
        return self.convert_adc_to_resistance(raw_rtd, self.rref)

    def read_temperature(self) -> float:
        """读取 RTD 当前温度，单位为摄氏度。"""
        raw_rtd = self.read_raw_rtd()
        return self.convert_adc_to_temperature(raw_rtd, self.rref, self.r0)

    def clear_faults(self) -> None:
        """清除故障状态位。"""
        config = self.read_register(MAX31865_CONFIG_REG)
        self.write_register(MAX31865_CONFIG_REG, config | MAX31865_CONFIG_FAULT_CLEAR)

    def read_register(self, reg_addr: int) -> int:
        """读取单个寄存器。"""
        command = [reg_addr & 0x7F, 0x00]
        response = self._spi_read(command)
        return response[1]

    def read_registers(self, reg_addr: int, length: int) -> List[int]:
        """从指定寄存器开始连续读取多个字节。

        返回:
            list[int]: 读取到的寄存器字节列表
        """
        if length <= 0:
            return []
        command = [reg_addr & 0x7F] + ([0x00] * length)
        response = self._spi_read(command)
        return response[1:]

    def write_register(self, reg_addr: int, value: int) -> None:
        """写入单个寄存器。"""
        command = [(reg_addr | 0x80) & 0xFF, value & 0xFF]
        self._spi_write(command)

    def write_registers(self, reg_addr: int, values: List[int]) -> None:
        """从指定寄存器开始连续写入多个字节。"""
        if not isinstance(values, list):
            raise TypeError("values must be a list of int")
        command = [(reg_addr | 0x80) & 0xFF] + [value & 0xFF for value in values]
        self._spi_write(command)

    def close(self) -> None:
        """关闭底层 SPI 设备。

        注意:
            该操作会调用传入 `SoftSPI` 实例的 `close()`。
        """
        if self._closed:
            return
        self.spi.close()
        self._closed = True

    def __enter__(self) -> "MAX31865":
        """支持 with 上下文管理。"""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """退出上下文时自动关闭设备。"""
        self.close()
