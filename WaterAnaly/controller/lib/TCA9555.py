"""TCA9555 I2C GPIO expander driver."""

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
    """TCA9555 驱动。"""

    def __init__(self, i2c_bus: int = TCA9555_DEFAULT_I2C_BUS, addr: int = TCA9555_DEFAULT_ADDR):
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
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed or self.bus is None:
            raise RuntimeError("TCA9555 device is closed")

    def _read_byte(self, register: int) -> int:
        self._ensure_open()
        try:
            return self.bus.read_byte_data(self.addr, register)
        except Exception:
            logger.exception("Failed to read TCA9555 register 0x%02X", register)
            raise

    def _write_byte(self, register: int, value: int) -> None:
        self._ensure_open()
        try:
            self.bus.write_byte_data(self.addr, register, value & 0xFF)
        except Exception:
            logger.exception("Failed to write TCA9555 register 0x%02X = 0x%02X", register, value & 0xFF)
            raise

    def _read_register_pair(self, start_register: int) -> int:
        low = self._read_byte(start_register)
        high = self._read_byte(start_register + 1)
        return low | (high << 8)

    def _write_register_pair(self, start_register: int, value: int) -> None:
        low = value & 0xFF
        high = (value >> 8) & 0xFF
        self._write_byte(start_register, low)
        self._write_byte(start_register + 1, high)

    def _normalize_pins(self, pins: TCA9555_PinArg) -> List[int]:
        if isinstance(pins, int):
            pins = [pins]
        elif isinstance(pins, list):
            pins = pins
        else:
            raise TypeError("pins must be an int or a list[int]")

        if not pins:
            raise ValueError("pin list cannot be empty")
        if not all(isinstance(pin, int) for pin in pins):
            raise TypeError("all pins must be integers")

        # 这里顺手去重，避免上层重复传同一个 pin。
        unique_pins = []  # type: List[int]
        seen = set()
        for pin in pins:
            if pin < 0 or pin > 15:
                raise ValueError("invalid pin number: %s, expected 0~15" % pin)
            if pin not in seen:
                unique_pins.append(pin)
                seen.add(pin)
        return unique_pins

    def _normalize_mode(self, mode: str) -> int:
        if mode == "input":
            return 1
        if mode == "output":
            return 0
        raise ValueError("mode must be 'input' or 'output'")

    def _normalize_bool_value(self, value: Union[bool, int]) -> bool:
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        raise ValueError("value must be bool, 0, or 1")

    def _build_mask_by_port(self, pins: List[int]) -> tuple:
        # TCA9555 分成两个 8 位端口，这里把 pin 列表转换成位掩码。
        mask0 = 0
        mask1 = 0
        for pin in pins:
            if pin < 8:
                mask0 |= 1 << pin
            else:
                mask1 |= 1 << (pin - 8)
        return mask0, mask1

    def _write_masked_register_pair(self, start_register: int, current_value: int, mask: int, set_bits: bool) -> int:
        if set_bits:
            new_value = current_value | mask
        else:
            new_value = current_value & ~mask

        if new_value != current_value:
            changed_low = (current_value & 0x00FF) != (new_value & 0x00FF)
            changed_high = (current_value & 0xFF00) != (new_value & 0xFF00)

            if changed_low:
                self._write_byte(start_register, new_value & 0xFF)
            if changed_high:
                self._write_byte(start_register + 1, (new_value >> 8) & 0xFF)

        return new_value

    def ping(self) -> bool:
        """读取一次输入寄存器，确认设备在线。"""
        self._read_byte(TCA9555_REG_INPUT_PORT0)
        return True

    def set_mode(self, pins: TCA9555_PinArg, mode: TCA9555_Mode) -> None:
        """设置单个或多个 IO 的方向。"""
        pins = self._normalize_pins(pins)
        bit_value = self._normalize_mode(mode)
        mask0, mask1 = self._build_mask_by_port(pins)
        mask = mask0 | (mask1 << 8)

        if bit_value == 1:
            self.config_state = self._write_masked_register_pair(TCA9555_REG_CONFIG_PORT0, self.config_state, mask, True)
        else:
            self.config_state = self._write_masked_register_pair(TCA9555_REG_CONFIG_PORT0, self.config_state, mask, False)

        logger.debug("Set mode %s for pins %s -> config=0x%04X", mode, pins, self.config_state)

    def write(self, pins: TCA9555_PinArg, value: Union[bool, int]) -> None:
        """写单个或多个 IO 的输出锁存值。"""
        pins = self._normalize_pins(pins)
        state = self._normalize_bool_value(value)
        mask0, mask1 = self._build_mask_by_port(pins)
        mask = mask0 | (mask1 << 8)

        self.output_state = self._write_masked_register_pair(TCA9555_REG_OUTPUT_PORT0, self.output_state, mask, state)
        logger.debug("Write %s to pins %s -> output=0x%04X", state, pins, self.output_state)

    def read(self, pins: TCA9555_PinArg, source: TCA9555_ReadSource = "input") -> Union[bool, List[bool]]:
        """读取单个或多个 IO 状态。"""
        normalized_pins = self._normalize_pins(pins)
        word = self.read_word(source=source)
        values = [bool(word & (1 << pin)) for pin in normalized_pins]
        if isinstance(pins, int):
            return values[0]
        return values

    def write_port(self, port: int, value: int) -> None:
        """按端口写 8 位输出值。"""
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
        """按端口读取 8 位值。"""
        if port not in (0, 1):
            raise ValueError("port must be 0 or 1")
        if source == "input":
            base_reg = TCA9555_REG_INPUT_PORT0
        elif source == "output":
            base_reg = TCA9555_REG_OUTPUT_PORT0
        else:
            raise ValueError("source must be 'input' or 'output'")
        return self._read_byte(base_reg + port)

    def write_word(self, value: int) -> None:
        """一次写入 16 位输出值。"""
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0 or value > 0xFFFF:
            raise ValueError("value must be in range 0x0000~0xFFFF")

        if value != self.output_state:
            self._write_register_pair(TCA9555_REG_OUTPUT_PORT0, value)
        self.output_state = value
        logger.debug("Write word 0x%04X", self.output_state)

    def read_word(self, source: TCA9555_ReadSource = "input") -> int:
        """一次读取 16 位值。"""
        if source == "input":
            base_reg = TCA9555_REG_INPUT_PORT0
        elif source == "output":
            base_reg = TCA9555_REG_OUTPUT_PORT0
        else:
            raise ValueError("source must be 'input' or 'output'")
        return self._read_register_pair(base_reg)

    def set_polarity(self, pins: TCA9555_PinArg, inverted: Union[bool, int]) -> None:
        """设置输入极性反转。"""
        pins = self._normalize_pins(pins)
        invert = self._normalize_bool_value(inverted)
        mask0, mask1 = self._build_mask_by_port(pins)
        mask = mask0 | (mask1 << 8)

        self.polarity_state = self._write_masked_register_pair(TCA9555_REG_POLARITY_PORT0, self.polarity_state, mask, invert)
        logger.debug("Set polarity inverted=%s for pins %s -> polarity=0x%04X", invert, pins, self.polarity_state)

    def close(self) -> None:
        """关闭 I2C 总线。"""
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
