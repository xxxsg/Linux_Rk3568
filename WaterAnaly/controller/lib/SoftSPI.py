"""基于通用 Pin 抽象的软件 SPI 总线实现。"""

from __future__ import annotations

from typing import Iterable, List

from lib.pins import Pin


class SoftSPI:
    """一个简单的 SPI Mode 0 软件时序助手。

    该类依赖 4 个实现了 `Pin` 接口的引脚对象，支持软件方式完成
    `cs/sclk/mosi/miso` 时序控制。
    """

    def __init__(
        self,
        sclk: Pin,
        mosi: Pin,
        miso: Pin,
        cs: Pin,
    ) -> None:
        """初始化 SPI 引脚，并将总线置于空闲状态。

        参数:
            sclk: SPI 时钟引脚，应工作在输出模式
            mosi: 主发从收引脚，应工作在输出模式
            miso: 主收从发引脚，应工作在输入模式
            cs: 片选引脚，应工作在输出模式
        """
        self._closed = False
        self.sclk = self._require_pin("sclk", sclk, "output")
        self.mosi = self._require_pin("mosi", mosi, "output")
        self.miso = self._require_pin("miso", miso, "input")
        self.cs = self._require_pin("cs", cs, "output")

        self.sclk.low()
        self.mosi.low()
        self.cs.high()

    def _require_pin(self, name: str, pin: Pin, mode: str) -> Pin:
        """校验引脚对象，并按用途切换输入/输出模式。"""
        if not isinstance(pin, Pin):
            raise TypeError("%s must be a Pin instance" % name)
        if mode == "output":
            pin.set_output()
        else:
            pin.set_input()
        return pin

    def _ensure_open(self) -> None:
        """确保 SoftSPI 还没有被关闭。"""
        if self._closed:
            raise RuntimeError("SoftSPI bus is closed")

    def cs_low(self) -> None:
        """拉低片选，开始一次 SPI 事务。"""
        self._ensure_open()
        self.cs.low()

    def cs_high(self) -> None:
        """拉高片选，结束一次 SPI 事务。"""
        self._ensure_open()
        self.cs.high()

    def transfer_byte(self, data: int) -> int:
        """按 SPI Mode 0 时序发送 1 字节，并同时读回 1 字节。

        参数:
            data: 待发送字节，内部会按 `0xFF` 截断

        返回:
            int: 从设备返回的 1 字节数据
        """
        self._ensure_open()
        tx = int(data) & 0xFF
        rx = 0

        for bit in range(7, -1, -1):
            # 先在时钟低电平准备数据，再在上升沿采样 MISO。
            self.sclk.low()
            self.mosi.write((tx >> bit) & 0x01)
            self.sclk.high()
            rx = (rx << 1) | int(self.miso.read())

        self.sclk.low()
        return rx

    def transfer(self, data: Iterable[int]) -> List[int]:
        """连续传输多个字节，并返回每个字节对应的读回值。

        参数:
            data: 可迭代字节序列

        返回:
            list[int]: 与输入长度一致的读回结果
        """
        self._ensure_open()
        return [self.transfer_byte(value) for value in data]

    def write(self, data: Iterable[int]) -> None:
        """仅写数据，忽略读回结果。

        参数:
            data: 可迭代字节序列
        """
        self.transfer(data)

    def read(self, length: int, fill: int = 0x00) -> List[int]:
        """读取指定字节数，期间通过 fill 持续输出占位字节。

        参数:
            length: 需要读取的字节数，必须大于等于 0
            fill: 读取过程中发送给从设备的占位字节

        返回:
            list[int]: 读取到的字节列表
        """
        if length < 0:
            raise ValueError("length must be >= 0")
        return self.transfer([fill] * length)

    def close(self) -> None:
        """关闭软件 SPI 对象，仅标记状态，不主动释放引脚。

        注意:
            传入的 Pin 对象仍由调用方负责关闭。
        """
        if self._closed:
            return
        self._closed = True

    def __enter__(self) -> "SoftSPI":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
