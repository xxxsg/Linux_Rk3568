"""ADS1115 I2C ADC driver."""

from __future__ import annotations

import time

try:
    import smbus2 as smbus
except ImportError:  # pragma: no cover
    import smbus  # type: ignore[no-redef]


ADS1115_IIC_ADDRESS0 = 0x48
ADS1115_IIC_ADDRESS1 = 0x49

ADS1115_DEFAULT_BUS = 1
ADS1115_DEFAULT_ADDR = ADS1115_IIC_ADDRESS0

ADS1115_REG_POINTER_CONVERT = 0x00
ADS1115_REG_POINTER_CONFIG = 0x01
ADS1115_REG_POINTER_LOWTHRESH = 0x02
ADS1115_REG_POINTER_HITHRESH = 0x03

ADS1115_REG_CONFIG_OS_SINGLE = 0x80

ADS1115_REG_CONFIG_MUX_DIFF_0_1 = 0x00
ADS1115_REG_CONFIG_MUX_DIFF_0_3 = 0x10
ADS1115_REG_CONFIG_MUX_DIFF_1_3 = 0x20
ADS1115_REG_CONFIG_MUX_DIFF_2_3 = 0x30

ADS1115_REG_CONFIG_MUX_SINGLE_0 = 0x40
ADS1115_REG_CONFIG_MUX_SINGLE_1 = 0x50
ADS1115_REG_CONFIG_MUX_SINGLE_2 = 0x60
ADS1115_REG_CONFIG_MUX_SINGLE_3 = 0x70

ADS1115_REG_CONFIG_PGA_6_144V = 0x00
ADS1115_REG_CONFIG_PGA_4_096V = 0x02
ADS1115_REG_CONFIG_PGA_2_048V = 0x04
ADS1115_REG_CONFIG_PGA_1_024V = 0x06
ADS1115_REG_CONFIG_PGA_0_512V = 0x08
ADS1115_REG_CONFIG_PGA_0_256V = 0x0A

ADS1115_REG_CONFIG_MODE_CONTIN = 0x00
ADS1115_REG_CONFIG_MODE_SINGLE = 0x01

ADS1115_REG_CONFIG_DR_8SPS = 0x00
ADS1115_REG_CONFIG_DR_16SPS = 0x20
ADS1115_REG_CONFIG_DR_32SPS = 0x40
ADS1115_REG_CONFIG_DR_64SPS = 0x60
ADS1115_REG_CONFIG_DR_128SPS = 0x80
ADS1115_REG_CONFIG_DR_250SPS = 0xA0
ADS1115_REG_CONFIG_DR_475SPS = 0xC0
ADS1115_REG_CONFIG_DR_860SPS = 0xE0

ADS1115_REG_CONFIG_CMODE_TRAD = 0x00
ADS1115_REG_CONFIG_CMODE_WINDOW = 0x10
ADS1115_REG_CONFIG_CPOL_ACTVLOW = 0x00
ADS1115_REG_CONFIG_CPOL_ACTVHI = 0x08
ADS1115_REG_CONFIG_CLAT_NONLAT = 0x00
ADS1115_REG_CONFIG_CLAT_LATCH = 0x04
ADS1115_REG_CONFIG_CQUE_1CONV = 0x00
ADS1115_REG_CONFIG_CQUE_2CONV = 0x01
ADS1115_REG_CONFIG_CQUE_4CONV = 0x02
ADS1115_REG_CONFIG_CQUE_NONE = 0x03

ADS1115_GAIN_TO_COEFFICIENT = {
    ADS1115_REG_CONFIG_PGA_6_144V: 0.1875,
    ADS1115_REG_CONFIG_PGA_4_096V: 0.125,
    ADS1115_REG_CONFIG_PGA_2_048V: 0.0625,
    ADS1115_REG_CONFIG_PGA_1_024V: 0.03125,
    ADS1115_REG_CONFIG_PGA_0_512V: 0.015625,
    ADS1115_REG_CONFIG_PGA_0_256V: 0.0078125,
}

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

ADS1115_CONVERSION_DELAY_S = 0.1


class ADS1115:
    """ADS1115 驱动。"""

    def __init__(self, i2c_bus: int = ADS1115_DEFAULT_BUS, addr: int = ADS1115_DEFAULT_ADDR):
        """初始化 ADS1115。

        参数:
            bus_num: I2C 总线号
            addr: I2C 地址
        """
        if not isinstance(i2c_bus, int):
            raise TypeError("i2c_bus must be an integer")
        if i2c_bus < 0:
            raise ValueError("i2c_bus must be >= 0")
        if not isinstance(addr, int):
            raise TypeError("addr must be an integer")
        if addr < 0x03 or addr > 0x77:
            raise ValueError("addr must be in range 0x03~0x77")

        self.i2c_bus_num = i2c_bus
        self.addr = addr
        self.bus = smbus.SMBus(self.i2c_bus_num)
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

    def _build_single_config(self, channel: int) -> list:
        return [
            ADS1115_REG_CONFIG_OS_SINGLE
            | ADS1115_SINGLE_MUX_MAP[channel]
            | self.gain
            | ADS1115_REG_CONFIG_MODE_CONTIN,
            ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE,
        ]

    def _build_differential_config(self, channel: int) -> list:
        return [
            ADS1115_REG_CONFIG_OS_SINGLE
            | ADS1115_DIFFERENTIAL_MUX_MAP[channel]
            | self.gain
            | ADS1115_REG_CONFIG_MODE_CONTIN,
            ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE,
        ]

    def _write_config(self, config: list) -> None:
        self._ensure_open()
        self.bus.write_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONFIG, config)

    def _read_conversion(self) -> int:
        self._ensure_open()
        data = self.bus.read_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONVERT, 2)
        raw = (data[0] << 8) | data[1]
        if raw > 32767:
            raw -= 65536
        return raw

    def _raw_to_voltage_mv(self, raw_value: int) -> int:
        return int(float(raw_value) * self.coefficient)

    def ping(self) -> bool:
        # 通过一次最小读操作确认设备在线。
        self._ensure_open()
        self.bus.read_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONVERT, 2)
        return True

    def set_address(self, addr: int) -> None:
        """设置 I2C 地址。"""
        if not isinstance(addr, int):
            raise TypeError("addr must be an integer")
        if addr < 0x03 or addr > 0x77:
            raise ValueError("addr must be in range 0x03~0x77")
        self.addr = addr

    def set_gain(self, gain: int) -> None:
        """设置 PGA 增益。"""
        if not isinstance(gain, int):
            raise TypeError("gain must be an integer")
        if gain not in ADS1115_GAIN_TO_COEFFICIENT:
            raise ValueError("gain must be one of ADS1115_REG_CONFIG_PGA_* constants")
        self.gain = gain
        self.coefficient = ADS1115_GAIN_TO_COEFFICIENT[self.gain]

    def set_channel(self, channel: int) -> int:
        """设置默认通道。"""
        if not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if channel not in ADS1115_SINGLE_MUX_MAP:
            raise ValueError("channel must be in range 0~3")
        self.channel = channel
        return self.channel

    def read_raw(self, channel: int) -> int:
        """读取单端原始值。"""
        channel = self.set_channel(channel)
        self._write_config(self._build_single_config(channel))
        time.sleep(ADS1115_CONVERSION_DELAY_S)
        return self._read_conversion()

    def read_voltage(self, channel: int) -> int:
        """读取单端电压，单位 mV。"""
        return self._raw_to_voltage_mv(self.read_raw(channel))

    def read_differential_raw(self, channel: int) -> int:
        """读取差分原始值。"""
        channel = self.set_channel(channel)
        self._write_config(self._build_differential_config(channel))
        time.sleep(ADS1115_CONVERSION_DELAY_S)
        return self._read_conversion()

    def read_differential_voltage(self, channel: int) -> int:
        """读取差分电压，单位 mV。"""
        return self._raw_to_voltage_mv(self.read_differential_raw(channel))

    def close(self) -> None:
        """关闭 I2C 连接。"""
        if self._closed:
            return

        try:
            self.bus.close()
        finally:
            self.bus = None
            self._closed = True
