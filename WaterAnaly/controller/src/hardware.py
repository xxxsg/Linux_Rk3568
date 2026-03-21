from __future__ import annotations

import os
import sys
from typing import Any, Dict


# 允许直接从 `src` 目录运行脚本时导入上一级 `lib`。
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lib.ADS1115 import ADS1115, ADS1115_REG_CONFIG_PGA_4_096V
from lib.MAX31865 import MAX31865
from lib.SoftSPI import SoftSPI
from lib.TCA9555 import TCA9555
from lib.pins import GpiodPin, Tca9555Pin
from lib.pump import Pump
from lib.stepper import Stepper


# 这里直接沿用 test.py 中已经验证过的硬件定义，便于保持一致。
TCA9555_BUS = 1
TCA9555_ADDR = 0x20
TCA9555_CTRL_ADDR = 0x21
ADS1115_BUS = 1
ADS1115_ADDR = 0x48

# TCA9555 输出引脚定义。
PIN_DISSOLVER = 0
PIN_STD_1 = 1
PIN_STD_2 = 2
PIN_SAMPLE = 3
PIN_ANALYSIS_WASTE = 4
PIN_REAGENT_A = 5
PIN_REAGENT_B = 6
PIN_REAGENT_C = 7
PIN_CLEAN_WASTE = 8
PIN_DISSOLVER_UP = 9
PIN_DISSOLVER_DOWN = 10
PIN_STEPPER_DIR = 0
PIN_STEPPER_ENA = 1

GPIO_STEPPER_PUL = ("/dev/gpiochip1", 1)

GPIO_MAX31865_SCLK = ("/dev/gpiochip3", 5)
GPIO_MAX31865_MOSI = ("/dev/gpiochip1", 0)
GPIO_MAX31865_MISO = ("/dev/gpiochip3", 4)
GPIO_MAX31865_CS = ("/dev/gpiochip3", 3)

# 统一保留阀门命名，供流程层直接引用。
VALVE_PIN_ORDER = [
    ("dissolver", PIN_DISSOLVER),
    ("std_1", PIN_STD_1),
    ("std_2", PIN_STD_2),
    ("sample", PIN_SAMPLE),
    ("analysis_waste", PIN_ANALYSIS_WASTE),
    ("reagent_a", PIN_REAGENT_A),
    ("reagent_b", PIN_REAGENT_B),
    ("reagent_c", PIN_REAGENT_C),
    ("clean_waste", PIN_CLEAN_WASTE),
    ("dissolver_up", PIN_DISSOLVER_UP),
    ("dissolver_down", PIN_DISSOLVER_DOWN),
]


def init_hardware() -> Dict[str, Any]:
    """按 test.py 的风格初始化硬件对象。"""

    tca9555 = TCA9555(i2c_bus=TCA9555_BUS, addr=TCA9555_ADDR)
    tca9555_ctrl = TCA9555(i2c_bus=TCA9555_BUS, addr=TCA9555_CTRL_ADDR)
    ads1115 = ADS1115(i2c_bus=ADS1115_BUS, addr=ADS1115_ADDR)
    ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)

    valves: Dict[str, Tca9555Pin] = {}
    valves["dissolver"] = Tca9555Pin(tca9555, PIN_DISSOLVER, initial_value=False)
    valves["std_1"] = Tca9555Pin(tca9555, PIN_STD_1, initial_value=False)
    valves["std_2"] = Tca9555Pin(tca9555, PIN_STD_2, initial_value=False)
    valves["sample"] = Tca9555Pin(tca9555, PIN_SAMPLE, initial_value=False)
    valves["analysis_waste"] = Tca9555Pin(tca9555, PIN_ANALYSIS_WASTE, initial_value=False)
    valves["reagent_a"] = Tca9555Pin(tca9555, PIN_REAGENT_A, initial_value=False)
    valves["reagent_b"] = Tca9555Pin(tca9555, PIN_REAGENT_B, initial_value=False)
    valves["reagent_c"] = Tca9555Pin(tca9555, PIN_REAGENT_C, initial_value=False)
    valves["clean_waste"] = Tca9555Pin(tca9555, PIN_CLEAN_WASTE, initial_value=False)
    valves["dissolver_up"] = Tca9555Pin(tca9555, PIN_DISSOLVER_UP, initial_value=False)
    valves["dissolver_down"] = Tca9555Pin(tca9555, PIN_DISSOLVER_DOWN, initial_value=False)

    pul_pin = GpiodPin(
        GPIO_STEPPER_PUL,
        consumer="recipe_stepper_pul",
        default_value=False,
    )
    dir_pin = Tca9555Pin(tca9555_ctrl, PIN_STEPPER_DIR, initial_value=False)
    ena_pin = Tca9555Pin(tca9555_ctrl, PIN_STEPPER_ENA, initial_value=True)

    stepper = Stepper(
        pul_pin=pul_pin,
        dir_pin=dir_pin,
        ena_pin=ena_pin,
        steps_per_rev=800,
    )
    stepper.configure_driver(
        dir_high_forward=True,
        ena_low_enable=True,
        auto_enable=True,
    )
    stepper.set_rpm(300)

    pump = Pump(driver=stepper, aspirate_direction="reverse")

    spi = SoftSPI(
        sclk=GpiodPin(
            GPIO_MAX31865_SCLK,
            consumer="recipe_max31865_sclk",
            default_value=False,
        ),
        mosi=GpiodPin(
            GPIO_MAX31865_MOSI,
            consumer="recipe_max31865_mosi",
            default_value=False,
        ),
        miso=GpiodPin(
            GPIO_MAX31865_MISO,
            consumer="recipe_max31865_miso",
            mode="input",
        ),
        cs=GpiodPin(
            GPIO_MAX31865_CS,
            consumer="recipe_max31865_cs",
            default_value=True,
        ),
    )
    max31865 = MAX31865(
        spi=spi,
        rref=430.0,
        r0=100.0,
        wires=2,
        filter_frequency=50,
    )

    return {
        "tca9555": tca9555,
        "tca9555_ctrl": tca9555_ctrl,
        "ads1115": ads1115,
        "valves": valves,
        "stepper": stepper,
        "pump": pump,
        "spi": spi,
        "max31865": max31865,
    }


def cleanup_hardware(hw: Dict[str, Any] | None) -> None:
    """按 test.py 的清理顺序释放资源。"""

    if not hw:
        return

    ads1115 = hw.get("ads1115")
    if ads1115 is not None:
        try:
            ads1115.close()
        except Exception:
            pass

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

    tca9555_ctrl = hw.get("tca9555_ctrl")
    if tca9555_ctrl is not None:
        try:
            tca9555_ctrl.close()
        except Exception:
            pass


# 为现有流程文件保留兼容入口，内部直接复用 test 风格实现。
def build_hardware(_config=None) -> Dict[str, Any]:
    return init_hardware()


def safe_shutdown(hw: Dict[str, Any] | None) -> None:
    cleanup_hardware(hw)
