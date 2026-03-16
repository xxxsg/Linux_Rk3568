"""ADS1115 I2C ADC driver."""

from __future__ import annotations

import time

try:
    import smbus2 as smbus
except ImportError:  # pragma: no cover
    import smbus  # type: ignore[no-redef]


# ==================== I2C 地址 ====================
ADS1115_IIC_ADDRESS0 = 0x48
ADS1115_IIC_ADDRESS1 = 0x49

# ==================== 默认配置 ====================
ADS1115_DEFAULT_BUS = 1
ADS1115_DEFAULT_ADDR = ADS1115_IIC_ADDRESS0

# ==================== 寄存器地址 ====================
ADS1115_REG_POINTER_CONVERT = 0x00
ADS1115_REG_POINTER_CONFIG = 0x01
ADS1115_REG_POINTER_LOWTHRESH = 0x02
ADS1115_REG_POINTER_HITHRESH = 0x03

# ==================== 配置寄存器位定义 ====================
# OS 位
ADS1115_REG_CONFIG_OS_NOEFFECT = 0x00
ADS1115_REG_CONFIG_OS_SINGLE = 0x80

# MUX: 差分输入
ADS1115_REG_CONFIG_MUX_DIFF_0_1 = 0x00
ADS1115_REG_CONFIG_MUX_DIFF_0_3 = 0x10
ADS1115_REG_CONFIG_MUX_DIFF_1_3 = 0x20
ADS1115_REG_CONFIG_MUX_DIFF_2_3 = 0x30

# MUX: 单端输入
ADS1115_REG_CONFIG_MUX_SINGLE_0 = 0x40
ADS1115_REG_CONFIG_MUX_SINGLE_1 = 0x50
ADS1115_REG_CONFIG_MUX_SINGLE_2 = 0x60
ADS1115_REG_CONFIG_MUX_SINGLE_3 = 0x70

# PGA: 输入量程/增益
ADS1115_REG_CONFIG_PGA_6_144V = 0x00
ADS1115_REG_CONFIG_PGA_4_096V = 0x02
ADS1115_REG_CONFIG_PGA_2_048V = 0x04
ADS1115_REG_CONFIG_PGA_1_024V = 0x06
ADS1115_REG_CONFIG_PGA_0_512V = 0x08
ADS1115_REG_CONFIG_PGA_0_256V = 0x0A

# MODE
ADS1115_REG_CONFIG_MODE_CONTIN = 0x00
ADS1115_REG_CONFIG_MODE_SINGLE = 0x01

# DR: 采样率
ADS1115_REG_CONFIG_DR_8SPS = 0x00
ADS1115_REG_CONFIG_DR_16SPS = 0x20
ADS1115_REG_CONFIG_DR_32SPS = 0x40
ADS1115_REG_CONFIG_DR_64SPS = 0x60
ADS1115_REG_CONFIG_DR_128SPS = 0x80
ADS1115_REG_CONFIG_DR_250SPS = 0xA0
ADS1115_REG_CONFIG_DR_475SPS = 0xC0
ADS1115_REG_CONFIG_DR_860SPS = 0xE0

# Comparator mode
ADS1115_REG_CONFIG_CMODE_TRAD = 0x00
ADS1115_REG_CONFIG_CMODE_WINDOW = 0x10

# Comparator polarity
ADS1115_REG_CONFIG_CPOL_ACTVLOW = 0x00
ADS1115_REG_CONFIG_CPOL_ACTVHI = 0x08

# Latch
ADS1115_REG_CONFIG_CLAT_NONLAT = 0x00
ADS1115_REG_CONFIG_CLAT_LATCH = 0x04

# Comparator queue
ADS1115_REG_CONFIG_CQUE_1CONV = 0x00
ADS1115_REG_CONFIG_CQUE_2CONV = 0x01
ADS1115_REG_CONFIG_CQUE_4CONV = 0x02
ADS1115_REG_CONFIG_CQUE_NONE = 0x03

# ==================== 增益与量程换算系数 ====================
ADS1115_GAIN_TO_COEFFICIENT = {
    ADS1115_REG_CONFIG_PGA_6_144V: 0.1875,
    ADS1115_REG_CONFIG_PGA_4_096V: 0.125,
    ADS1115_REG_CONFIG_PGA_2_048V: 0.0625,
    ADS1115_REG_CONFIG_PGA_1_024V: 0.03125,
    ADS1115_REG_CONFIG_PGA_0_512V: 0.015625,
    ADS1115_REG_CONFIG_PGA_0_256V: 0.0078125,
}

# ==================== 通道与 MUX 对应关系 ====================
ADS1115_SINGLE_MUX_MAP = {
    0: ADS1115_REG_CONFIG_MUX_SINGLE_0,
    1: ADS1115_REG_CONFIG_MUX_SINGLE_1,
    2: ADS1115_REG_CONFIG_MUX_SINGLE_2,
    3: ADS1115_REG_CONFIG_MUX_SINGLE_3,
}

ADS1115_DIFFERENTIAL_MUX_MAP = {
    0: ADS1115_REG_CONFIG_MUX_DIFF_0_1,
    1: ADS1115_REG_CONFIG_MUX_DIFF_0_3,
    2: ADS1115_REG_CONFIG_MUX_DIFF_1_3,
    3: ADS1115_REG_CONFIG_MUX_DIFF_2_3,
}


class ADS1115:
    """ADS1115 模数转换器驱动。

    提供单端输入、差分输入、电压换算和 I2C 生命周期管理等常用能力。
    """

    def __init__(self, bus_num: int = ADS1115_DEFAULT_BUS, addr: int = ADS1115_DEFAULT_ADDR):
        """初始化 ADS1115 设备。

        参数:
            bus_num: I2C 总线号，默认 `1`。
            addr: I2C 设备地址，默认 `0x48`。
        """
        self.bus_num = self._normalize_bus_num(bus_num)
        self.addr = self._normalize_address(addr)
        self.bus = smbus.SMBus(self.bus_num)
        self.gain = ADS1115_REG_CONFIG_PGA_2_048V
        self.coefficient = ADS1115_GAIN_TO_COEFFICIENT[self.gain]
        self.channel = 0
        self._closed = False

    def __enter__(self) -> "ADS1115":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed or self.bus is None:
            raise RuntimeError("ADS1115 device is closed")

    def _normalize_bus_num(self, bus_num: int) -> int:
        if not isinstance(bus_num, int):
            raise TypeError("bus_num must be an integer")
        if bus_num < 0:
            raise ValueError("bus_num must be >= 0")
        return bus_num

    def _normalize_address(self, addr: int) -> int:
        if not isinstance(addr, int):
            raise TypeError("addr must be an integer")
        if addr < 0x03 or addr > 0x77:
            raise ValueError("addr must be a valid 7-bit I2C address in range 0x03~0x77")
        return addr

    def _normalize_channel(self, channel: int) -> int:
        if not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if channel not in ADS1115_SINGLE_MUX_MAP:
            raise ValueError("channel must be in range 0~3")
        return channel

    def _normalize_gain(self, gain: int) -> int:
        if not isinstance(gain, int):
            raise TypeError("gain must be an integer")
        if gain not in ADS1115_GAIN_TO_COEFFICIENT:
            raise ValueError("gain must be one of ADS1115_REG_CONFIG_PGA_* constants")
        return gain

    def _build_single_config(self, channel: int) -> list[int]:
        # 单端输入配置:
        # channel 0~3 分别对应 AIN0~AIN3 对 GND。
        return [
            ADS1115_REG_CONFIG_OS_SINGLE
            | ADS1115_SINGLE_MUX_MAP[channel]
            | self.gain
            | ADS1115_REG_CONFIG_MODE_CONTIN,
            ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE,
        ]

    def _build_differential_config(self, channel: int) -> list[int]:
        # 差分输入配置:
        # 0: AIN0-AIN1
        # 1: AIN0-AIN3
        # 2: AIN1-AIN3
        # 3: AIN2-AIN3
        return [
            ADS1115_REG_CONFIG_OS_SINGLE
            | ADS1115_DIFFERENTIAL_MUX_MAP[channel]
            | self.gain
            | ADS1115_REG_CONFIG_MODE_CONTIN,
            ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE,
        ]

    def _write_config(self, config: list[int]) -> None:
        self._ensure_open()
        self.bus.write_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONFIG, config)

    def _read_conversion(self) -> int:
        self._ensure_open()
        data = self.bus.read_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONVERT, 2)
        raw = (data[0] << 8) | data[1]
        if raw > 32767:
            raw -= 65536
        return raw

    def _conversion_delay_seconds(self) -> float:
        # 保留原始库约 100ms 的等待策略，避免改变现有采样节奏。
        return 0.1

    def _raw_to_voltage_mv(self, raw_value: int) -> int:
        return int(float(raw_value) * self.coefficient)

    def set_address(self, addr: int) -> None:
        """设置 ADS1115 的 I2C 地址。

        参数:
            addr: 7 位 I2C 地址，范围 `0x03~0x77`。
        """
        self.addr = self._normalize_address(addr)

    def set_gain(self, gain: int) -> None:
        """设置 PGA 增益和输入量程。

        参数:
            gain: 使用 `ADS1115_REG_CONFIG_PGA_*` 常量之一。
        """
        self.gain = self._normalize_gain(gain)
        self.coefficient = ADS1115_GAIN_TO_COEFFICIENT[self.gain]

    def set_channel(self, channel: int) -> int:
        """设置当前默认通道。

        参数:
            channel: 通道号 `0~3`。

        返回:
            校验后的通道号。
        """
        self.channel = self._normalize_channel(channel)
        return self.channel

    def read_raw(self, channel: int) -> int:
        """读取单端输入原始 ADC 值。

        参数:
            channel: 单端输入通道 `0~3`，分别对应 `AIN0~AIN3` 对 `GND`。
        """
        normalized_channel = self.set_channel(channel)
        self._write_config(self._build_single_config(normalized_channel))
        time.sleep(self._conversion_delay_seconds())
        return self._read_conversion()

    def read_voltage(self, channel: int) -> int:
        """读取单端输入电压。

        参数:
            channel: 单端输入通道 `0~3`。

        返回:
            电压值，单位为毫伏。
        """
        return self._raw_to_voltage_mv(self.read_raw(channel))

    def read_differential_raw(self, channel: int) -> int:
        """读取差分输入原始 ADC 值。

        参数:
            channel: 差分输入编号 `0~3`。
            `0/1/2/3` 分别对应 `AIN0-AIN1`、`AIN0-AIN3`、`AIN1-AIN3`、`AIN2-AIN3`。
        """
        normalized_channel = self.set_channel(channel)
        self._write_config(self._build_differential_config(normalized_channel))
        time.sleep(self._conversion_delay_seconds())
        return self._read_conversion()

    def read_differential_voltage(self, channel: int) -> int:
        """读取差分输入电压。

        参数:
            channel: 差分输入编号 `0~3`。

        返回:
            电压值，单位为毫伏。
        """
        return self._raw_to_voltage_mv(self.read_differential_raw(channel))

    def close(self) -> None:
        """关闭 I2C 设备句柄。"""
        if self._closed:
            return

        try:
            self.bus.close()
        finally:
            self.bus = None
            self._closed = True
