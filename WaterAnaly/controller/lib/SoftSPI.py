"""Software SPI bus implemented with gpiod GPIO lines."""

from __future__ import annotations

from typing import TypeAlias

import gpiod


PinSpec: TypeAlias = tuple[str, int]


class SoftSPI:
    """基于 gpiod 的软件 SPI 总线。

    适用于硬件 SPI 不方便使用、且 SCLK/MOSI/MISO/CS 可能分布在不同 gpiochip
    上的场景。每根线使用 `(chip, line)` 二元组描述。
    """

    def __init__(self, sclk: PinSpec, mosi: PinSpec, miso: PinSpec, cs: PinSpec):
        """初始化软件 SPI 总线。

        参数:
            sclk: 时钟线 `(chip, line)`。
            mosi: 主发从收线 `(chip, line)`。
            miso: 主收从发线 `(chip, line)`。
            cs: 片选线 `(chip, line)`。
        """
        self._closed = False
        self._chips: dict[str, gpiod.Chip] = {}

        self.sclk = self._normalize_pin_spec("sclk", sclk)
        self.mosi = self._normalize_pin_spec("mosi", mosi)
        self.miso = self._normalize_pin_spec("miso", miso)
        self.cs = self._normalize_pin_spec("cs", cs)

        self.line_sclk = self._request_output_line(self.sclk, "max31865_soft_spi_sclk", 0)
        self.line_mosi = self._request_output_line(self.mosi, "max31865_soft_spi_mosi", 0)
        self.line_miso = self._request_input_line(self.miso, "max31865_soft_spi_miso")
        self.line_cs = self._request_output_line(self.cs, "max31865_soft_spi_cs", 1)

    def _normalize_pin_spec(self, name: str, pin_spec: PinSpec) -> PinSpec:
        if not isinstance(pin_spec, tuple) or len(pin_spec) != 2:
            raise TypeError(f"{name} must be a tuple of (chip, line)")

        chip_name, line_offset = pin_spec
        if not isinstance(chip_name, str) or not chip_name:
            raise TypeError(f"{name} chip must be a non-empty string")
        if not isinstance(line_offset, int):
            raise TypeError(f"{name} line must be an integer")
        if line_offset < 0:
            raise ValueError(f"{name} line must be >= 0")
        return chip_name, line_offset

    def _get_chip(self, chip_name: str) -> gpiod.Chip:
        chip = self._chips.get(chip_name)
        if chip is None:
            chip = gpiod.Chip(chip_name)
            self._chips[chip_name] = chip
        return chip

    def _request_output_line(self, pin_spec: PinSpec, consumer: str, default_value: int):
        chip_name, line_offset = pin_spec
        chip = self._get_chip(chip_name)
        line = chip.get_line(line_offset)
        line.request(
            consumer=consumer,
            type=gpiod.LINE_REQ_DIR_OUT,
            default_vals=[default_value],
        )
        return line

    def _request_input_line(self, pin_spec: PinSpec, consumer: str):
        chip_name, line_offset = pin_spec
        chip = self._get_chip(chip_name)
        line = chip.get_line(line_offset)
        line.request(
            consumer=consumer,
            type=gpiod.LINE_REQ_DIR_IN,
        )
        return line

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SoftSPI bus is closed")

    def cs_low(self) -> None:
        """拉低片选信号。"""
        self._ensure_open()
        self.line_cs.set_value(0)

    def cs_high(self) -> None:
        """拉高片选信号。"""
        self._ensure_open()
        self.line_cs.set_value(1)

    def transfer_byte(self, data: int) -> int:
        """发送并接收一个字节。

        参数:
            data: 待发送的 8 位数据。

        返回:
            从 MISO 线上读到的 8 位数据。
        """
        self._ensure_open()
        tx = int(data) & 0xFF
        rx = 0

        for bit in range(7, -1, -1):
            self.line_sclk.set_value(0)
            self.line_mosi.set_value((tx >> bit) & 0x01)
            self.line_sclk.set_value(1)
            rx = (rx << 1) | (self.line_miso.get_value() & 0x01)

        self.line_sclk.set_value(0)
        return rx

    def transfer(self, data: list[int]) -> list[int]:
        """连续发送并接收多个字节。

        参数:
            data: 待发送字节列表。

        返回:
            与发送长度一致的接收字节列表。
        """
        self._ensure_open()
        if not isinstance(data, list):
            raise TypeError("data must be a list of int")

        return [self.transfer_byte(value) for value in data]

    def close(self) -> None:
        """释放所有 GPIO line 和 chip 资源。"""
        if self._closed:
            return

        for line_name in ("line_sclk", "line_mosi", "line_miso", "line_cs"):
            line = getattr(self, line_name, None)
            if line is None:
                continue
            try:
                line.release()
            except Exception:
                pass

        for chip in self._chips.values():
            try:
                chip.close()
            except Exception:
                pass

        self._chips.clear()
        self._closed = True

    def __enter__(self) -> "SoftSPI":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
