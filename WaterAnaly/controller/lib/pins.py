"""输出脚相关类。

这个文件集中放三类内容：
- OutputPin: 统一的输出脚接口
- GpiodPin: SoC GPIO 版本
- Tca9555Pin: TCA9555 版本
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple, TYPE_CHECKING

import gpiod

if TYPE_CHECKING:
    from lib.TCA9555 import TCA9555

PinSpec = Tuple[str, int]


class OutputPin(ABC):
    """所有输出脚都遵守的最小接口。"""

    @abstractmethod
    def write(self, value: bool) -> None:
        """写入逻辑电平。True 表示高，False 表示低。"""

    def high(self) -> None:
        """输出高电平。"""
        self.write(True)

    def low(self) -> None:
        """输出低电平。"""
        self.write(False)

    @abstractmethod
    def close(self) -> None:
        """释放底层资源。"""


class GpiodPin(OutputPin):
    """基于 gpiod 1.4 的输出脚。

    参数 `pin` 使用 `(chip, line)` 元组，风格与 SoftSPI 保持一致。
    """

    def __init__(
        self,
        pin: PinSpec,
        consumer: str = "motorlib",
        active_high: bool = True,
        default_value: bool = False,
    ) -> None:
        self._pin = self._normalize_pin_spec("pin", pin)
        if not isinstance(consumer, str) or not consumer:
            raise ValueError("consumer 必须是非空字符串")

        chip_name, line_offset = self._pin
        self._active_high = bool(active_high)
        self._closed = False
        self._chip = gpiod.Chip(chip_name)
        self._line = self._chip.get_line(line_offset)
        self._line.request(
            consumer=consumer,
            type=gpiod.LINE_REQ_DIR_OUT,
            default_vals=[self._to_physical_value(default_value)],
        )

    def _normalize_pin_spec(self, name: str, pin_spec: PinSpec) -> PinSpec:
        if not isinstance(pin_spec, tuple) or len(pin_spec) != 2:
            raise TypeError("%s 必须是 (chip, line) 元组" % name)

        chip_name, line_offset = pin_spec
        if not isinstance(chip_name, str) or not chip_name:
            raise TypeError("%s 的 chip 必须是非空字符串" % name)
        if not isinstance(line_offset, int):
            raise TypeError("%s 的 line 必须是整数" % name)
        if line_offset < 0:
            raise ValueError("%s 的 line 必须大于等于 0" % name)
        return chip_name, line_offset

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("GpiodPin 已关闭")

    def _to_physical_value(self, value: bool) -> int:
        logical_value = bool(value)
        if self._active_high:
            return 1 if logical_value else 0
        return 0 if logical_value else 1

    def write(self, value: bool) -> None:
        """写入逻辑电平。"""
        self._ensure_open()
        self._line.set_value(self._to_physical_value(value))

    def close(self) -> None:
        """释放 gpiod line 和 chip。"""
        if self._closed:
            return

        try:
            if self._line is not None:
                self._line.release()
        finally:
            self._line = None
            try:
                if self._chip is not None:
                    self._chip.close()
            finally:
                self._chip = None
                self._closed = True

    def __enter__(self) -> "GpiodPin":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class Tca9555Pin(OutputPin):
    """把 TCA9555 的单个 pin 包装成统一输出脚。"""

    def __init__(
        self,
        device: "TCA9555",
        pin: int,
        active_high: bool = True,
        initial_value: bool = False,
    ) -> None:
        if device is None:
            raise ValueError("device 不能为空")
        if not isinstance(pin, int) or pin < 0 or pin > 15:
            raise ValueError("pin 必须是 0 到 15 之间的整数")

        self._device = device
        self._pin = pin
        self._active_high = bool(active_high)
        self._closed = False

        self._device.set_mode(self._pin, "output")
        self.write(initial_value)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Tca9555Pin 已关闭")

    def _to_physical_value(self, value: bool) -> bool:
        logical_value = bool(value)
        if self._active_high:
            return logical_value
        return not logical_value

    def write(self, value: bool) -> None:
        """写入逻辑电平。"""
        self._ensure_open()
        self._device.write(self._pin, self._to_physical_value(value))

    def close(self) -> None:
        """关闭当前 pin 对象，不关闭外部 TCA9555 设备。"""
        self._closed = True
