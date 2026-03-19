#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""测试硬件接线初始化。

当前先只按文件注释完成接线和对象初始化，方便后续继续补测试流程。
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Any


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lib.MAX31865 import MAX31865
from lib.SoftSPI import SoftSPI
from lib.TCA9555 import TCA9555
from lib.pins import GpiodPin, Tca9555Pin
from lib.pump import Pump
from lib.stepper import Stepper


TCA9555_BUS = 1
TCA9555_ADDR = 0x20

# TCA9555-1 输出引脚
PIN_DISSOLVER = 0  # 消解器
PIN_STD_1 = 1  # 标一
PIN_STD_2 = 2  # 标二
PIN_SAMPLE = 3  # 水样
PIN_ANALYSIS_WASTE = 4  # 分析废液

PIN_REAGENT_A = 5  # A液
PIN_REAGENT_B = 6  # B液
PIN_REAGENT_C = 7  # C液
PIN_CLEAN_WASTE = 8  # 清洗废液

PIN_DISSOLVER_UP = 9  # 消解器-上
PIN_DISSOLVER_DOWN = 10  # 消解器-下

PIN_STEPPER_DIR = 14  # 蠕动泵方向 DIR
PIN_STEPPER_ENA = 15  # 蠕动泵使能 ENA

# 板载 GPIO
GPIO_STEPPER_PUL = ("/dev/gpiochip1", 1)  # 蠕动泵脉冲 PUL

GPIO_MAX31865_SCLK = ("/dev/gpiochip3", 5)  # MAX31865 时钟 SCLK
GPIO_MAX31865_MOSI = ("/dev/gpiochip1", 0)  # MAX31865 主出从入 MOSI
GPIO_MAX31865_MISO = ("/dev/gpiochip3", 4)  # MAX31865 主入从出 MISO
GPIO_MAX31865_CS = ("/dev/gpiochip3", 3)  # MAX31865 片选 CS


def init_hardware() -> Dict[str, Any]:
    """按当前接线表初始化全部测试对象。"""
    tca9555 = TCA9555(
        i2c_bus=TCA9555_BUS,  # I2C 总线 1
        addr=TCA9555_ADDR,  # TCA9555-1 地址 0x20
    )

    valve_pins = {
        "dissolver": Tca9555Pin(tca9555, PIN_DISSOLVER, initial_value=False),  # 消解器
        "std_1": Tca9555Pin(tca9555, PIN_STD_1, initial_value=False),  # 标一
        "std_2": Tca9555Pin(tca9555, PIN_STD_2, initial_value=False),  # 标二
        "sample": Tca9555Pin(tca9555, PIN_SAMPLE, initial_value=False),  # 水样
        "analysis_waste": Tca9555Pin(tca9555, PIN_ANALYSIS_WASTE, initial_value=False),  # 分析废液
        "reagent_a": Tca9555Pin(tca9555, PIN_REAGENT_A, initial_value=False),  # A液
        "reagent_b": Tca9555Pin(tca9555, PIN_REAGENT_B, initial_value=False),  # B液
        "reagent_c": Tca9555Pin(tca9555, PIN_REAGENT_C, initial_value=False),  # C液
        "clean_waste": Tca9555Pin(tca9555, PIN_CLEAN_WASTE, initial_value=False),  # 清洗废液
        "dissolver_up": Tca9555Pin(tca9555, PIN_DISSOLVER_UP, initial_value=False),  # 消解器-上
        "dissolver_down": Tca9555Pin(tca9555, PIN_DISSOLVER_DOWN, initial_value=False),  # 消解器-下
    }

    pul_pin = GpiodPin(
        GPIO_STEPPER_PUL,  # PUL: /dev/gpiochip1 line1
        consumer="test_stepper_pul",  # 蠕动泵脉冲输出
        default_value=False,  # 上电默认低电平
    )
    dir_pin = Tca9555Pin(
        tca9555,  # TCA9555-1 设备
        PIN_STEPPER_DIR,  # DIR: 14
        initial_value=False,  # 默认方向为低
    )
    ena_pin = Tca9555Pin(
        tca9555,  # TCA9555-1 设备
        PIN_STEPPER_ENA,  # ENA: 15
        initial_value=True,  # 默认先禁用驱动
    )

    stepper = Stepper(
        pul_pin=pul_pin,  # PUL 脉冲脚
        dir_pin=dir_pin,  # DIR 方向脚
        ena_pin=ena_pin,  # ENA 使能脚
        steps_per_rev=800,  # 驱动细分后的每圈步数
    )
    stepper.configure_driver(
        dir_high_forward=True,  # DIR 高电平为正转
        ena_low_enable=True,  # ENA 低电平为使能
        auto_enable=True,  # 运动时自动使能
    )
    stepper.set_rpm(300)  # 默认转速 300 RPM

    pump = Pump(
        driver=stepper,  # 蠕动泵底层步进驱动
        aspirate_direction="reverse",  # 吸液方向定义为反转
    )

    spi = SoftSPI(
        sclk=GpiodPin(
            GPIO_MAX31865_SCLK,  # SCLK: /dev/gpiochip3 line5
            consumer="test_max31865_sclk",  # 软件 SPI 时钟
            default_value=False,  # 默认低电平
        ),
        mosi=GpiodPin(
            GPIO_MAX31865_MOSI,  # MOSI: /dev/gpiochip1 line0
            consumer="test_max31865_mosi",  # 软件 SPI 数据输出
            default_value=False,  # 默认低电平
        ),
        miso=GpiodPin(
            GPIO_MAX31865_MISO,  # MISO: /dev/gpiochip3 line4
            consumer="test_max31865_miso",  # 软件 SPI 数据输入
            mode="input",  # 输入模式
        ),
        cs=GpiodPin(
            GPIO_MAX31865_CS,  # CS: /dev/gpiochip3 line3
            consumer="test_max31865_cs",  # MAX31865 片选
            default_value=True,  # 默认拉高不选中
        ),
    )
    max31865 = MAX31865(
        spi=spi,  # 软件 SPI 总线
        rref=430.0,  # 参考电阻 430 欧
        r0=100.0,  # PT100 标称电阻
        wires=2,  # 两线制 PT100
        filter_frequency=50,  # 50Hz 工频滤波
    )

    return {
        "tca9555": tca9555,
        "valves": valve_pins,
        "stepper": stepper,
        "pump": pump,
        "spi": spi,
        "max31865": max31865,
    }


def cleanup_hardware(hw: Dict[str, Any]) -> None:
    """关闭初始化过程中申请的硬件资源。"""
    if not hw:
        return

    max31865 = hw.get("max31865")
    if max31865 is not None:
        try:
            max31865.close()
        except Exception:
            pass

    pump = hw.get("pump")
    if pump is not None:
        try:
            pump.cleanup()
        except Exception:
            pass

    for pin in hw.get("valves", {}).values():
        try:
            pin.close()
        except Exception:
            pass

    tca9555 = hw.get("tca9555")
    if tca9555 is not None:
        try:
            tca9555.close()
        except Exception:
            pass


def main() -> None:
    hw = init_hardware()
    try:
        print("硬件接线初始化完成。")
        print("可用对象: valves / stepper / pump / max31865")
    finally:
        cleanup_hardware(hw)


if __name__ == "__main__":
    main()
