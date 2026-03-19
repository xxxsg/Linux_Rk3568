"""ADS1115 I2C ADC 驱动。"""

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
    """ADS1115 I2C ADC 驱动。

    提供单端和差分采样，并将原始 ADC 值换算为毫伏。
    """

    def __init__(self, i2c_bus: int = ADS1115_DEFAULT_BUS, addr: int = ADS1115_DEFAULT_ADDR):
        """初始化 ADS1115 设备并打开指定 I2C 总线。"""
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
        """确保底层 I2C 设备仍然可用。"""
        if self._closed or self.bus is None:
            raise RuntimeError("ADS1115 device is closed")

    def _read_conversion(self) -> int:
        """读取转换寄存器，并转成有符号 16 位结果。"""
        self._ensure_open()
        data = self.bus.read_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONVERT, 2)
        raw = (data[0] << 8) | data[1]
        if raw > 32767:
            raw -= 65536
        return raw

    def _build_config(self, channel: int, *, differential: bool) -> list[int]:
        """按通道和采样模式拼出配置寄存器的两个字节。"""
        mux_map = ADS1115_DIFFERENTIAL_MUX_MAP if differential else ADS1115_SINGLE_MUX_MAP
        return [
            ADS1115_REG_CONFIG_OS_SINGLE | mux_map[channel] | self.gain | ADS1115_REG_CONFIG_MODE_SINGLE,
            ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE,
        ]

    def _start_conversion(self, channel: int, *, differential: bool) -> None:
        """写入配置寄存器并等待一次转换完成。"""
        self._ensure_open()
        config = self._build_config(channel, differential=differential)
        self.bus.write_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONFIG, config)
        time.sleep(ADS1115_CONVERSION_DELAY_S)

    def _read_channel_raw(self, channel: int, *, differential: bool) -> int:
        """统一封装通道选择、启动转换和读取原始值。"""
        channel = self.set_channel(channel)
        self._start_conversion(channel, differential=differential)
        return self._read_conversion()

    def _raw_to_voltage_mv(self, raw_value: int) -> int:
        """根据当前增益把原始值换算为毫伏。"""
        return int(float(raw_value) * self.coefficient)

    def ping(self) -> bool:
        """尝试读取设备，成功则说明 I2C 通信正常。"""
        self._ensure_open()
        self.bus.read_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONVERT, 2)
        return True

    def set_address(self, addr: int) -> None:
        """更新当前设备地址，不重新打开总线。"""
        if not isinstance(addr, int):
            raise TypeError("addr must be an integer")
        if addr < 0x03 or addr > 0x77:
            raise ValueError("addr must be in range 0x03~0x77")
        self.addr = addr

    def set_gain(self, gain: int) -> None:
        """设置 PGA 增益，同时更新原始值到毫伏的换算系数。"""
        if not isinstance(gain, int):
            raise TypeError("gain must be an integer")
        if gain not in ADS1115_GAIN_TO_COEFFICIENT:
            raise ValueError("gain must be one of ADS1115_REG_CONFIG_PGA_* constants")
        self.gain = gain
        self.coefficient = ADS1115_GAIN_TO_COEFFICIENT[self.gain]

    def set_channel(self, channel: int) -> int:
        """设置当前通道编号，范围为 0~3。"""
        if not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if channel not in ADS1115_SINGLE_MUX_MAP:
            raise ValueError("channel must be in range 0~3")
        self.channel = channel
        return self.channel

    def read_raw(self, channel: int) -> int:
        """读取单端通道的原始 ADC 值。"""
        return self._read_channel_raw(channel, differential=False)

    def read_voltage(self, channel: int) -> int:
        """读取单端通道电压，返回毫伏。"""
        raw_value = self._read_channel_raw(channel, differential=False)
        return self._raw_to_voltage_mv(raw_value)

    def read_differential_raw(self, channel: int) -> int:
        """读取差分通道的原始 ADC 值。"""
        return self._read_channel_raw(channel, differential=True)

    def read_differential_voltage(self, channel: int) -> int:
        """读取差分通道电压，返回毫伏。"""
        raw_value = self._read_channel_raw(channel, differential=True)
        return self._raw_to_voltage_mv(raw_value)

    def close(self) -> None:
        """关闭 I2C 句柄，重复调用安全。"""
        if self._closed:
            return

        try:
            self.bus.close()
        finally:
            self.bus = None
            self._closed = True
