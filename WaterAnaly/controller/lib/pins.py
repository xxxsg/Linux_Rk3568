"""控制器库共用的 GPIO 引脚抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal, Tuple

import gpiod

if TYPE_CHECKING:
    from lib.TCA9555 import TCA9555

PinMode = Literal["input", "output"]
PinSpec = Tuple[str, int]


class Pin(ABC):
    """最小化的双向引脚接口。

    上层模块只依赖这组抽象方法，从而同时兼容本地 GPIO 和扩展 IO。
    """

    @abstractmethod
    def set_mode(self, mode: PinMode, *, default_value: bool = False) -> None:
        """切换引脚方向。"""

    def set_output(self, default_value: bool = False) -> None:
        """将引脚切换为输出模式。"""
        self.set_mode("output", default_value=default_value)

    def set_input(self) -> None:
        """将引脚切换为输入模式。"""
        self.set_mode("input")

    @abstractmethod
    def write(self, value: bool) -> None:
        """输出指定逻辑电平。"""

    @abstractmethod
    def read(self) -> bool:
        """读取当前逻辑电平。"""

    def high(self) -> None:
        """`write(True)` 的便捷封装。"""
        self.write(True)

    def low(self) -> None:
        """`write(False)` 的便捷封装。"""
        self.write(False)

    @abstractmethod
    def close(self) -> None:
        """释放底层 GPIO 资源。"""


class GpiodPin(Pin):
    """基于 libgpiod 的本地 GPIO 引脚实现。

    支持逻辑电平与物理电平映射，可通过 `active_high` 适配高低有效设备。
    """

    def __init__(
        self,
        pin: PinSpec,
        consumer: str = "motorlib",
        active_high: bool = True,
        default_value: bool = False,
        mode: PinMode = "output",
    ) -> None:
        """创建并初始化一个 libgpiod 引脚对象。

        参数:
            pin: `(chip, line)` 形式的引脚描述
            consumer: libgpiod consumer 名称
            active_high: 是否高电平表示逻辑 True
            default_value: 输出模式下的默认逻辑电平
            mode: 初始方向，`"input"` 或 `"output"`
        """
        self._pin = self._normalize_pin_spec("pin", pin)
        if not isinstance(consumer, str) or not consumer:
            raise ValueError("consumer must be a non-empty string")

        self._consumer = consumer
        self._active_high = bool(active_high)
        self._closed = False
        self._mode: PinMode | None = None
        self._chip = gpiod.Chip(self._pin[0])
        self._line = self._chip.get_line(self._pin[1])
        self.set_mode(mode, default_value=default_value)

    @staticmethod
    def _normalize_pin_spec(name: str, pin_spec: PinSpec) -> PinSpec:
        """校验并规范化 `(chip, line)` 形式的引脚描述。"""
        if not isinstance(pin_spec, tuple) or len(pin_spec) != 2:
            raise TypeError("%s must be a tuple of (chip, line)" % name)

        chip_name, line_offset = pin_spec
        if not isinstance(chip_name, str) or not chip_name:
            raise TypeError("%s chip must be a non-empty string" % name)
        if not isinstance(line_offset, int):
            raise TypeError("%s line must be an integer" % name)
        if line_offset < 0:
            raise ValueError("%s line must be >= 0" % name)
        return chip_name, line_offset

    def _ensure_open(self) -> None:
        """确保引脚尚未被关闭。"""
        if self._closed:
            raise RuntimeError("GpiodPin is closed")

    def _to_physical_value(self, value: bool) -> int:
        """将逻辑电平转换为实际输出电平。"""
        logical_value = bool(value)
        if self._active_high:
            return 1 if logical_value else 0
        return 0 if logical_value else 1

    def _to_logical_value(self, value: int) -> bool:
        """将实际电平转换为逻辑电平。"""
        physical_value = bool(value)
        return physical_value if self._active_high else not physical_value

    def set_mode(self, mode: PinMode, *, default_value: bool = False) -> None:
        """重新申请引脚方向，并在输出模式下设置默认电平。"""
        self._ensure_open()
        if mode not in ("input", "output"):
            raise ValueError("mode must be 'input' or 'output'")

        try:
            self._line.release()
        except Exception:
            pass

        if mode == "output":
            self._line.request(
                consumer=self._consumer,
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[self._to_physical_value(default_value)],
            )
        else:
            self._line.request(
                consumer=self._consumer,
                type=gpiod.LINE_REQ_DIR_IN,
            )
        self._mode = mode

    def write(self, value: bool) -> None:
        """向引脚输出逻辑电平。"""
        self._ensure_open()
        if self._mode != "output":
            raise RuntimeError("pin is not configured as output")
        self._line.set_value(self._to_physical_value(value))

    def read(self) -> bool:
        """读取引脚当前逻辑电平。"""
        self._ensure_open()
        return self._to_logical_value(self._line.get_value())

    def close(self) -> None:
        """释放 line 与 chip 资源。"""
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
                self._mode = None

    def __enter__(self) -> "GpiodPin":
        """支持 with 上下文管理。"""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """退出上下文时自动关闭引脚。"""
        self.close()


class Tca9555Pin(Pin):
    """对 TCA9555 单个 IO 的引脚封装。

    让扩展 IO 能以与本地 GPIO 相同的 `Pin` 接口参与上层控制逻辑。
    """

    def __init__(
        self,
        device: "TCA9555",
        pin: int,
        active_high: bool = True,
        initial_value: bool = False,
        mode: PinMode = "output",
    ) -> None:
        """基于 TCA9555 设备创建一个逻辑引脚对象。

        参数:
            device: 底层 TCA9555 设备对象
            pin: 引脚号，范围 `0..15`
            active_high: 是否高电平表示逻辑 True
            initial_value: 输出模式下的默认逻辑电平
            mode: 初始方向，`"input"` 或 `"output"`
        """
        if device is None:
            raise ValueError("device is required")
        if not isinstance(pin, int) or pin < 0 or pin > 15:
            raise ValueError("pin must be an integer in range 0..15")

        self._device = device
        self._pin = pin
        self._active_high = bool(active_high)
        self._closed = False
        self._mode: PinMode | None = None
        self.set_mode(mode, default_value=initial_value)

    def _ensure_open(self) -> None:
        """确保引脚对象尚未关闭。"""
        if self._closed:
            raise RuntimeError("Tca9555Pin is closed")

    def _to_physical_value(self, value: bool) -> bool:
        """将逻辑电平转换为实际输出值。"""
        logical_value = bool(value)
        if self._active_high:
            return logical_value
        return not logical_value

    def _to_logical_value(self, value: bool) -> bool:
        """将实际读取值转换为逻辑电平。"""
        physical_value = bool(value)
        return physical_value if self._active_high else not physical_value

    def set_mode(self, mode: PinMode, *, default_value: bool = False) -> None:
        """设置 TCA9555 对应引脚方向。"""
        self._ensure_open()
        if mode not in ("input", "output"):
            raise ValueError("mode must be 'input' or 'output'")

        self._device.set_mode(self._pin, mode)
        self._mode = mode
        if mode == "output":
            self.write(default_value)

    def write(self, value: bool) -> None:
        """向扩展 IO 引脚输出逻辑电平。"""
        self._ensure_open()
        if self._mode != "output":
            raise RuntimeError("pin is not configured as output")
        self._device.write(self._pin, self._to_physical_value(value))

    def read(self) -> bool:
        """读取扩展 IO 引脚当前逻辑电平。"""
        self._ensure_open()
        source = "output" if self._mode == "output" else "input"
        return self._to_logical_value(self._device.read(self._pin, source=source))

    def close(self) -> None:
        """关闭当前引脚视图，不会关闭底层 TCA9555 设备。"""
        self._closed = True
        self._mode = None
