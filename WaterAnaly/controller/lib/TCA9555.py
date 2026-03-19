"""TCA9555 I2C GPIO 扩展芯片驱动。"""

from __future__ import annotations

import logging
from typing import List, Literal, Union

import smbus2


logger = logging.getLogger(__name__)


TCA9555_DEFAULT_I2C_BUS = 1
TCA9555_DEFAULT_ADDR = 0x20

TCA9555_REG_INPUT_PORT0 = 0x00
TCA9555_REG_INPUT_PORT1 = 0x01
TCA9555_REG_OUTPUT_PORT0 = 0x02
TCA9555_REG_OUTPUT_PORT1 = 0x03
TCA9555_REG_POLARITY_PORT0 = 0x04
TCA9555_REG_POLARITY_PORT1 = 0x05
TCA9555_REG_CONFIG_PORT0 = 0x06
TCA9555_REG_CONFIG_PORT1 = 0x07

TCA9555_PinArg = Union[int, List[int]]
TCA9555_Mode = Literal["input", "output"]
TCA9555_ReadSource = Literal["input", "output"]


class TCA9555:
    """TCA9555 I2C GPIO 扩展芯片驱动。

    提供 16 路扩展 IO 的方向配置、输出写入、输入读取和极性反转能力。
    """

    def __init__(self, i2c_bus: int = TCA9555_DEFAULT_I2C_BUS, addr: int = TCA9555_DEFAULT_ADDR):
        """打开 I2C 总线，并缓存配置/输出/极性寄存器状态。

        参数:
            i2c_bus: I2C 总线号，必须为非负整数
            addr: 设备 I2C 地址，必须位于 7 位地址合法范围内
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
        self.bus = smbus2.SMBus(self.i2c_bus_num)
        self._closed = False

        self.config_state = self._read_register_pair(TCA9555_REG_CONFIG_PORT0)
        self.output_state = self._read_register_pair(TCA9555_REG_OUTPUT_PORT0)
        self.polarity_state = self._read_register_pair(TCA9555_REG_POLARITY_PORT0)

        logger.debug(
            "TCA9555 initialized on bus=%s addr=0x%02X config=0x%04X output=0x%04X polarity=0x%04X",
            self.i2c_bus_num,
            self.addr,
            self.config_state,
            self.output_state,
            self.polarity_state,
        )

    def __enter__(self) -> "TCA9555":
        """支持 with 上下文管理。"""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """退出上下文时自动关闭设备。"""
        self.close()

    def _ensure_open(self) -> None:
        """确保设备尚未关闭。"""
        if self._closed or self.bus is None:
            raise RuntimeError("TCA9555 device is closed")

    def _read_byte(self, register: int) -> int:
        """读取单个寄存器字节。"""
        self._ensure_open()
        try:
            return self.bus.read_byte_data(self.addr, register)
        except Exception:
            logger.exception("Failed to read TCA9555 register 0x%02X", register)
            raise

    def _write_byte(self, register: int, value: int) -> None:
        """写入单个寄存器字节。"""
        self._ensure_open()
        try:
            self.bus.write_byte_data(self.addr, register, value & 0xFF)
        except Exception:
            logger.exception("Failed to write TCA9555 register 0x%02X = 0x%02X", register, value & 0xFF)
            raise

    def _read_register_pair(self, start_register: int) -> int:
        """连续读取两个寄存器并拼成 16 位值。"""
        low = self._read_byte(start_register)
        high = self._read_byte(start_register + 1)
        return low | (high << 8)

    def _write_register_pair(self, start_register: int, value: int) -> None:
        """将 16 位值拆分后写入两个连续寄存器。"""
        self._write_byte(start_register, value & 0xFF)
        self._write_byte(start_register + 1, (value >> 8) & 0xFF)

    def _normalize_pins(self, pins: TCA9555_PinArg) -> List[int]:
        """规范化单个或多个引脚参数，并去重。"""
        if isinstance(pins, int):
            normalized = [pins]
        elif isinstance(pins, list):
            normalized = pins
        else:
            raise TypeError("pins must be an int or a list[int]")

        if not normalized:
            raise ValueError("pin list cannot be empty")
        if not all(isinstance(pin, int) for pin in normalized):
            raise TypeError("all pins must be integers")

        unique_pins: List[int] = []
        seen = set()
        for pin in normalized:
            if pin < 0 or pin > 15:
                raise ValueError("invalid pin number: %s, expected 0~15" % pin)
            if pin in seen:
                continue
            unique_pins.append(pin)
            seen.add(pin)
        return unique_pins

    def _normalize_mode(self, mode: str) -> int:
        """将字符串模式转换为寄存器位定义。"""
        if mode == "input":
            return 1
        if mode == "output":
            return 0
        raise ValueError("mode must be 'input' or 'output'")

    def _normalize_bool_value(self, value: Union[bool, int]) -> bool:
        """接受 bool/0/1 三种输入形式。"""
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        raise ValueError("value must be bool, 0, or 1")

    def _build_mask(self, pins: List[int]) -> int:
        """根据引脚列表生成位掩码。"""
        mask = 0
        for pin in pins:
            mask |= 1 << pin
        return mask

    def _apply_mask(self, register: int, current_value: int, mask: int, enabled: bool) -> int:
        """按掩码更新寄存器缓存，并只写入发生变化的字节。"""
        new_value = (current_value | mask) if enabled else (current_value & ~mask)
        if new_value == current_value:
            return current_value

        changed_low = (current_value & 0x00FF) != (new_value & 0x00FF)
        changed_high = (current_value & 0xFF00) != (new_value & 0xFF00)

        if changed_low:
            self._write_byte(register, new_value & 0xFF)
        if changed_high:
            self._write_byte(register + 1, (new_value >> 8) & 0xFF)
        return new_value

    def _resolve_source_register(self, source: TCA9555_ReadSource) -> int:
        """根据读取来源返回对应寄存器地址。"""
        if source == "input":
            return TCA9555_REG_INPUT_PORT0
        if source == "output":
            return TCA9555_REG_OUTPUT_PORT0
        raise ValueError("source must be 'input' or 'output'")

    def ping(self) -> bool:
        """通过读取输入寄存器测试设备是否在线。"""
        self._read_byte(TCA9555_REG_INPUT_PORT0)
        return True

    def set_mode(self, pins: TCA9555_PinArg, mode: TCA9555_Mode) -> None:
        """设置指定引脚为输入或输出模式。

        参数:
            pins: 单个引脚号或引脚号列表，范围 `0..15`
            mode: `"input"` 或 `"output"`
        """
        normalized_pins = self._normalize_pins(pins)
        mask = self._build_mask(normalized_pins)
        use_input_mode = self._normalize_mode(mode) == 1
        self.config_state = self._apply_mask(TCA9555_REG_CONFIG_PORT0, self.config_state, mask, use_input_mode)
        logger.debug("Set mode %s for pins %s -> config=0x%04X", mode, normalized_pins, self.config_state)

    def write(self, pins: TCA9555_PinArg, value: Union[bool, int]) -> None:
        """向指定引脚写入逻辑电平。

        参数:
            pins: 单个引脚号或引脚号列表
            value: 允许传入 `True/False/1/0`
        """
        normalized_pins = self._normalize_pins(pins)
        mask = self._build_mask(normalized_pins)
        state = self._normalize_bool_value(value)
        self.output_state = self._apply_mask(TCA9555_REG_OUTPUT_PORT0, self.output_state, mask, state)
        logger.debug("Write %s to pins %s -> output=0x%04X", state, normalized_pins, self.output_state)

    def read(self, pins: TCA9555_PinArg, source: TCA9555_ReadSource = "input") -> Union[bool, List[bool]]:
        """读取指定引脚状态。

        参数:
            pins: 单个引脚号或引脚号列表
            source: `"input"` 读取输入寄存器，`"output"` 读取输出寄存器

        返回:
            bool | list[bool]: 单引脚返回布尔值，多引脚返回布尔列表
        """
        normalized_pins = self._normalize_pins(pins)
        word = self.read_word(source=source)
        values = [bool(word & (1 << pin)) for pin in normalized_pins]
        return values[0] if isinstance(pins, int) else values

    def write_port(self, port: int, value: int) -> None:
        """按端口写入 8 位输出值。

        参数:
            port: 端口号，只能为 `0` 或 `1`
            value: 8 位输出值，范围 `0x00..0xFF`
        """
        if port not in (0, 1):
            raise ValueError("port must be 0 or 1")
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0 or value > 0xFF:
            raise ValueError("value must be in range 0x00~0xFF")

        if port == 0:
            if (self.output_state & 0x00FF) != value:
                self._write_byte(TCA9555_REG_OUTPUT_PORT0, value)
            self.output_state = (self.output_state & 0xFF00) | value
        else:
            if ((self.output_state >> 8) & 0xFF) != value:
                self._write_byte(TCA9555_REG_OUTPUT_PORT1, value)
            self.output_state = (self.output_state & 0x00FF) | (value << 8)

        logger.debug("Write port %s = 0x%02X -> output=0x%04X", port, value, self.output_state)

    def read_port(self, port: int, source: TCA9555_ReadSource = "input") -> int:
        """读取单个 8 位端口值。

        参数:
            port: 端口号，只能为 `0` 或 `1`
            source: `"input"` 或 `"output"`

        返回:
            int: 端口的 8 位值
        """
        if port not in (0, 1):
            raise ValueError("port must be 0 or 1")
        base_register = self._resolve_source_register(source)
        return self._read_byte(base_register + port)

    def write_word(self, value: int) -> None:
        """一次性写入全部 16 位输出值。

        参数:
            value: 16 位输出值，范围 `0x0000..0xFFFF`
        """
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0 or value > 0xFFFF:
            raise ValueError("value must be in range 0x0000~0xFFFF")

        if value != self.output_state:
            self._write_register_pair(TCA9555_REG_OUTPUT_PORT0, value)
        self.output_state = value
        logger.debug("Write word 0x%04X", self.output_state)

    def read_word(self, source: TCA9555_ReadSource = "input") -> int:
        """一次性读取全部 16 位端口值。

        参数:
            source: `"input"` 或 `"output"`

        返回:
            int: 16 位端口值
        """
        return self._read_register_pair(self._resolve_source_register(source))

    def set_polarity(self, pins: TCA9555_PinArg, inverted: Union[bool, int]) -> None:
        """设置指定引脚输入极性是否反相。

        参数:
            pins: 单个引脚号或引脚号列表
            inverted: 允许传入 `True/False/1/0`
        """
        normalized_pins = self._normalize_pins(pins)
        mask = self._build_mask(normalized_pins)
        invert = self._normalize_bool_value(inverted)
        self.polarity_state = self._apply_mask(TCA9555_REG_POLARITY_PORT0, self.polarity_state, mask, invert)
        logger.debug("Set polarity inverted=%s for pins %s -> polarity=0x%04X", invert, normalized_pins, self.polarity_state)

    def close(self) -> None:
        """关闭底层 I2C 总线句柄。"""
        if self._closed:
            return

        try:
            self.bus.close()
        except Exception:
            logger.exception("Failed to close I2C bus for TCA9555")
            raise
        finally:
            self.bus = None
            self._closed = True
