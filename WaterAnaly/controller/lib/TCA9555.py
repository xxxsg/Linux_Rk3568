"""TCA9555 I2C GPIO expander driver."""

from __future__ import annotations

import logging
from typing import Literal, TypeAlias

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

TCA9555_PinArg: TypeAlias = int | list[int]
TCA9555_Mode: TypeAlias = Literal["input", "output"]
TCA9555_ReadSource: TypeAlias = Literal["input", "output"]


class TCA9555:
    """工程化版 TCA9555 驱动。

    设计原则：
    - 不在初始化时修改芯片 IO 模式或输出电平
    - 缓存 config/output/polarity 三组 16 位寄存器，减少 I2C 读写
    - 输入寄存器表示真实引脚电平，输出寄存器表示输出锁存值
    - 批量 pin 操作尽量合并为按端口的寄存器访问
    """

    def __init__(self, i2c_bus: int = TCA9555_DEFAULT_I2C_BUS, addr: int = TCA9555_DEFAULT_ADDR):
        self.i2c_bus_num = i2c_bus
        self.addr = addr
        self.bus = smbus2.SMBus(self.i2c_bus_num)
        self._closed = False

        # 缓存三个可写寄存器组，初始化时从芯片读取，避免擅自改硬件状态。
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

    def _normalize_pins(self, pin_or_pins: TCA9555_PinArg) -> list[int]:
        # 统一把 int / list[int] 规范成 list[int]，方便后续按端口合并访问。
        if isinstance(pin_or_pins, int):
            pins = [pin_or_pins]
        elif isinstance(pin_or_pins, list):
            pins = pin_or_pins
        else:
            raise TypeError("pin_or_pins must be an int or a list[int]")

        if not pins:
            raise ValueError("pin list cannot be empty")
        if not all(isinstance(pin, int) for pin in pins):
            raise TypeError("all pins must be integers")

        unique_pins: list[int] = []
        seen = set()
        for pin in pins:
            if pin < 0 or pin > 15:
                raise ValueError(f"invalid pin number: {pin}, expected 0~15")
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

    def _normalize_source(self, source: str) -> int:
        if source == "input":
            return TCA9555_REG_INPUT_PORT0
        if source == "output":
            return TCA9555_REG_OUTPUT_PORT0
        raise ValueError("source must be 'input' or 'output'")

    def _normalize_port(self, port: int) -> int:
        if port not in (0, 1):
            raise ValueError("port must be 0 or 1")
        return port

    def _normalize_word(self, value: int) -> int:
        if not isinstance(value, int):
            raise TypeError("value must be an integer")
        if value < 0 or value > 0xFFFF:
            raise ValueError("value must be in range 0x0000~0xFFFF")
        return value

    def _normalize_bool_value(self, value: bool | int) -> bool:
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        raise ValueError("value must be bool, 0, or 1")

    def _build_mask_by_port(self, pins: list[int]) -> tuple[int, int]:
        mask0 = 0
        mask1 = 0
        for pin in pins:
            if pin < 8:
                mask0 |= 1 << pin
            else:
                mask1 |= 1 << (pin - 8)
        return mask0, mask1

    def _write_masked_register_pair(self, start_register: int, current_value: int, mask: int, set_bits: bool) -> int:
        # 按位修改 16 位寄存器，仅对 mask 覆盖到的位进行更新。
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
        """探测设备是否在线。

        通过读取一次输入寄存器验证 I2C 通信是否正常。
        成功返回 True，失败直接抛出底层异常。
        """
        # 读一次输入寄存器验证设备在线，失败直接抛异常。
        self._read_byte(TCA9555_REG_INPUT_PORT0)
        return True

    def set_mode(self, pin_or_pins: TCA9555_PinArg, mode: TCA9555_Mode) -> None:
        """设置一个或多个 IO 的方向模式。

        参数:
            pin_or_pins: 单个 IO 编号，或 IO 编号列表，范围 0~15
            mode: `"input"` 或 `"output"`

        说明:
            该接口只修改配置寄存器，不会修改输出锁存值。
        """
        pins = self._normalize_pins(pin_or_pins)
        bit_value = self._normalize_mode(mode)
        mask0, mask1 = self._build_mask_by_port(pins)

        new_config = self.config_state
        if bit_value == 1:
            new_config = self._write_masked_register_pair(
                TCA9555_REG_CONFIG_PORT0,
                new_config,
                mask0 | (mask1 << 8),
                True,
            )
        else:
            new_config = self._write_masked_register_pair(
                TCA9555_REG_CONFIG_PORT0,
                new_config,
                mask0 | (mask1 << 8),
                False,
            )

        self.config_state = new_config
        logger.debug("Set mode %s for pins %s -> config=0x%04X", mode, pins, self.config_state)

    def write(self, pin_or_pins: TCA9555_PinArg, value: bool | int) -> None:
        """写一个或多个 IO 的输出锁存值。

        参数:
            pin_or_pins: 单个 IO 编号，或 IO 编号列表，范围 0~15
            value: `True`/`1` 表示高电平，`False`/`0` 表示低电平

        说明:
            该接口只写输出寄存器，不会隐式把 IO 切成输出模式。
            如需驱动引脚输出，请先调用 `set_mode(..., "output")`。
        """
        # 这里只写输出锁存寄存器，不隐式修改 IO 模式。
        pins = self._normalize_pins(pin_or_pins)
        state = self._normalize_bool_value(value)
        mask0, mask1 = self._build_mask_by_port(pins)
        mask = mask0 | (mask1 << 8)

        self.output_state = self._write_masked_register_pair(
            TCA9555_REG_OUTPUT_PORT0,
            self.output_state,
            mask,
            state,
        )
        logger.debug("Write %s to pins %s -> output=0x%04X", state, pins, self.output_state)

    def read(self, pin_or_pins: TCA9555_PinArg, source: TCA9555_ReadSource = "input") -> bool | list[bool]:
        """读取一个或多个 IO 的状态。

        参数:
            pin_or_pins: 单个 IO 编号，或 IO 编号列表，范围 0~15
            source: `"input"` 或 `"output"`

        返回:
            传入单个 `int` 时返回 `bool`
            传入 `list[int]` 时返回 `list[bool]`

        说明:
            - `source="input"`: 读取输入寄存器，表示真实引脚电平
            - `source="output"`: 读取输出寄存器，表示输出锁存值
        """
        pins = self._normalize_pins(pin_or_pins)
        word = self.read_word(source=source)
        values = [bool(word & (1 << pin)) for pin in pins]
        if isinstance(pin_or_pins, int):
            return values[0]
        return values

    def write_port(self, port: int, value: int) -> None:
        """按端口写入 8 位输出锁存值。

        参数:
            port: 端口号，只能是 `0` 或 `1`
            value: 8 位端口值，范围 `0x00 ~ 0xFF`

        说明:
            该接口只更新指定端口的输出寄存器，不会修改 IO 模式。
        """
        # port 写入 8 位值，仅更新指定端口的输出锁存寄存器。
        port = self._normalize_port(port)
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
        """按端口读取 8 位寄存器值。

        参数:
            port: 端口号，只能是 `0` 或 `1`
            source: `"input"` 或 `"output"`

        返回:
            0~255 的整数
        """
        port = self._normalize_port(port)
        base_reg = self._normalize_source(source)
        return self._read_byte(base_reg + port)

    def write_word(self, value: int) -> None:
        """一次写入 16 位输出锁存值。

        参数:
            value: 16 位字，范围 `0x0000 ~ 0xFFFF`

        说明:
            bit0 对应 P0，bit15 对应 P15。
            该接口只写输出寄存器，不会修改 IO 模式。
        """
        value = self._normalize_word(value)
        if value != self.output_state:
            self._write_register_pair(TCA9555_REG_OUTPUT_PORT0, value)
        self.output_state = value
        logger.debug("Write word 0x%04X", self.output_state)

    def read_word(self, source: TCA9555_ReadSource = "input") -> int:
        """一次读取 16 位寄存器值。

        参数:
            source: `"input"` 或 `"output"`

        返回:
            16 位整数，范围 `0x0000 ~ 0xFFFF`

        说明:
            - `source="input"`: 真实引脚电平
            - `source="output"`: 输出锁存值
        """
        base_reg = self._normalize_source(source)
        return self._read_register_pair(base_reg)

    def set_polarity(self, pin_or_pins: TCA9555_PinArg, inverted: bool | int) -> None:
        """设置一个或多个输入引脚的极性反转。

        参数:
            pin_or_pins: 单个 IO 编号，或 IO 编号列表，范围 0~15
            inverted: `True`/`1` 表示反转，`False`/`0` 表示不反转

        说明:
            该配置作用于极性反转寄存器。
        """
        pins = self._normalize_pins(pin_or_pins)
        invert = self._normalize_bool_value(inverted)
        mask0, mask1 = self._build_mask_by_port(pins)
        mask = mask0 | (mask1 << 8)

        self.polarity_state = self._write_masked_register_pair(
            TCA9555_REG_POLARITY_PORT0,
            self.polarity_state,
            mask,
            invert,
        )
        logger.debug("Set polarity inverted=%s for pins %s -> polarity=0x%04X", invert, pins, self.polarity_state)

    def close(self) -> None:
        """关闭 I2C 总线连接。

        该方法可重复调用；重复关闭会直接返回。
        关闭后再次访问设备会抛出 `RuntimeError`。
        """
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    # 最小示例：
    # 1. 打开设备
    # 2. 将 P0/P1 设为输出
    # 3. 输出锁存为高电平
    # 4. 读取真实输入电平和输出锁存值
    with TCA9555() as tca:
        tca.ping()
        tca.set_mode([0, 1], "output")
        tca.write([0, 1], True)
        input_levels = tca.read([0, 1], source="input")
        output_latch = tca.read([0, 1], source="output")
        logger.info("input_levels=%s output_latch=%s", input_levels, output_latch)
