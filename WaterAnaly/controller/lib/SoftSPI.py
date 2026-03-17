"""Software SPI bus implemented with gpiod GPIO lines."""

from __future__ import annotations

from typing import Dict, List, Tuple

import gpiod


PinSpec = Tuple[str, int]


class SoftSPI:
    """基于 gpiod 的软件 SPI。

    所有引脚都使用 `(chip, line)` 元组传入。
    """

    def __init__(self, sclk: PinSpec, mosi: PinSpec, miso: PinSpec, cs: PinSpec):
        """初始化软件 SPI。

        参数:
            sclk: 时钟脚，格式 `(chip, line)`
            mosi: 主发从收，格式 `(chip, line)`
            miso: 主收从发，格式 `(chip, line)`
            cs: 片选脚，格式 `(chip, line)`
        """
        self._closed = False
        self._chips = {}  # type: Dict[str, gpiod.Chip]

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
            raise TypeError("%s must be a tuple of (chip, line)" % name)

        chip_name, line_offset = pin_spec
        if not isinstance(chip_name, str) or not chip_name:
            raise TypeError("%s chip must be a non-empty string" % name)
        if not isinstance(line_offset, int):
            raise TypeError("%s line must be an integer" % name)
        if line_offset < 0:
            raise ValueError("%s line must be >= 0" % name)
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
        line.request(consumer=consumer, type=gpiod.LINE_REQ_DIR_OUT, default_vals=[default_value])
        return line

    def _request_input_line(self, pin_spec: PinSpec, consumer: str):
        chip_name, line_offset = pin_spec
        chip = self._get_chip(chip_name)
        line = chip.get_line(line_offset)
        line.request(consumer=consumer, type=gpiod.LINE_REQ_DIR_IN)
        return line

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SoftSPI bus is closed")

    def cs_low(self) -> None:
        self._ensure_open()
        self.line_cs.set_value(0)

    def cs_high(self) -> None:
        self._ensure_open()
        self.line_cs.set_value(1)

    def transfer_byte(self, data: int) -> int:
        """传输一个字节。"""
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

    def transfer(self, data: List[int]) -> List[int]:
        """连续传输多个字节。"""
        self._ensure_open()
        if not isinstance(data, list):
            raise TypeError("data must be a list of int")
        return [self.transfer_byte(value) for value in data]

    def close(self) -> None:
        """释放 GPIO line 和 chip。"""
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
