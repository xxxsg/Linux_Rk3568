from __future__ import annotations

import os
import sys
from dataclasses import dataclass


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import AppConfig, DEFAULT_CONFIG
from lib.ADS1115 import ADS1115
from lib.MAX31865 import MAX31865
from lib.SoftSPI import SoftSPI
from lib.TCA9555 import TCA9555
from lib.pins import GpiodPin, Tca9555Pin
from lib.pump import Pump
from lib.stepper import Stepper


VALVE_PIN_ORDER = list(DEFAULT_CONFIG.tca.valve_pins.items())

OPTICS_CTRL_PIN_ORDER = [
    ("meter_up", DEFAULT_CONFIG.tca.control_pins["meter_up"]),
    ("meter_down", DEFAULT_CONFIG.tca.control_pins["meter_down"]),
    ("digest_light", DEFAULT_CONFIG.tca.control_pins["digest_light"]),
    ("digest_ref_amp", DEFAULT_CONFIG.tca.control_pins["digest_ref_amp"]),
    ("digest_main_amp", DEFAULT_CONFIG.tca.control_pins["digest_main_amp"]),
]


class ValveBank:
    """液路阀组的轻量封装。

    流程层只需要表达“打开哪些阀”和“关闭所有阀”，
    不需要知道底层阀门是通过哪种 IO 设备驱动的。
    """

    def __init__(self, pins: dict[str, Tca9555Pin]) -> None:
        self._pins = pins

    @property
    def pins(self) -> dict[str, Tca9555Pin]:
        return self._pins

    def close_all(self) -> None:
        for pin in self._pins.values():
            pin.write(False)

    def open(self, names: list[str] | tuple[str, ...]) -> None:
        for name in names:
            self._pins[name].write(True)


class MeterOptics:
    """计量单元液位检测封装。"""

    def __init__(self, ads: ADS1115, upper_channel: int, lower_channel: int) -> None:
        self._ads = ads
        self._upper_channel = upper_channel
        self._lower_channel = lower_channel

    def read_upper_mv(self) -> float:
        return float(self._ads.read_voltage(self._upper_channel))

    def read_lower_mv(self) -> float:
        return float(self._ads.read_voltage(self._lower_channel))


class DigestOptics:
    """消解器读数通道封装。"""

    def __init__(self, ads: ADS1115, channel: int) -> None:
        self._ads = ads
        self._channel = channel

    def read_absorbance_mv(self) -> float:
        return float(self._ads.read_voltage(self._channel))


class TemperatureSensor:
    """温度读取封装。"""

    def __init__(self, probe: MAX31865) -> None:
        self._probe = probe

    def read_temperature_c(self) -> float:
        return float(self._probe.read_temperature())


@dataclass(frozen=True)
class HardwareContext:
    """流程运行时使用的硬件上下文。"""

    valve_io: TCA9555
    control_io: TCA9555
    ads1115: ADS1115
    valves: dict[str, Tca9555Pin]
    optics_controls: dict[str, Tca9555Pin]
    stepper: Stepper
    pump: Pump
    spi: SoftSPI
    max31865: MAX31865
    valve: ValveBank
    meter_optics: MeterOptics
    digest_optics: DigestOptics
    temp_sensor: TemperatureSensor


def _build_tca_pins(io: TCA9555, pin_map: dict[str, int]) -> dict[str, Tca9555Pin]:
    """按配置批量构建 TCA9555 输出 pin。"""

    pins: dict[str, Tca9555Pin] = {}
    for name, pin_no in pin_map.items():
        pins[name] = Tca9555Pin(io, pin_no, initial_value=False)
    return pins


def init_hardware(config: AppConfig = DEFAULT_CONFIG) -> HardwareContext:
    """按配置组装一份可直接供流程层使用的硬件上下文。"""

    valve_io = TCA9555(i2c_bus=config.tca.bus, addr=config.tca.valve_addr)
    control_io = TCA9555(i2c_bus=config.tca.bus, addr=config.tca.control_addr)
    ads1115 = ADS1115(i2c_bus=config.ads.bus, addr=config.ads.addr)
    ads1115.set_gain(config.ads.gain)

    valves = _build_tca_pins(valve_io, config.tca.valve_pins)
    optics_controls = _build_tca_pins(
        control_io,
        {
            "meter_up": config.tca.control_pins["meter_up"],
            "meter_down": config.tca.control_pins["meter_down"],
            "digest_light": config.tca.control_pins["digest_light"],
            "digest_ref_amp": config.tca.control_pins["digest_ref_amp"],
            "digest_main_amp": config.tca.control_pins["digest_main_amp"],
        },
    )

    pul_pin = GpiodPin(
        config.pump.pulse_pin,
        consumer="recipe_stepper_pul",
        default_value=False,
    )
    dir_pin = Tca9555Pin(
        control_io,
        config.tca.control_pins["stepper_dir"],
        initial_value=False,
    )
    ena_pin = Tca9555Pin(
        control_io,
        config.tca.control_pins["stepper_ena"],
        initial_value=True,
    )

    stepper = Stepper(
        pul_pin=pul_pin,
        dir_pin=dir_pin,
        ena_pin=ena_pin,
        steps_per_rev=config.pump.steps_per_rev,
    )
    stepper.configure_driver(
        dir_high_forward=True,
        ena_low_enable=True,
        auto_enable=True,
    )
    stepper.set_rpm(config.pump.rpm)

    pump = Pump(driver=stepper, aspirate_direction=config.pump.aspirate_direction)

    spi = SoftSPI(
        sclk=GpiodPin(
            config.temperature.sclk_pin,
            consumer="recipe_max31865_sclk",
            default_value=False,
        ),
        mosi=GpiodPin(
            config.temperature.mosi_pin,
            consumer="recipe_max31865_mosi",
            default_value=False,
        ),
        miso=GpiodPin(
            config.temperature.miso_pin,
            consumer="recipe_max31865_miso",
            mode="input",
        ),
        cs=GpiodPin(
            config.temperature.cs_pin,
            consumer="recipe_max31865_cs",
            default_value=True,
        ),
    )
    max31865 = MAX31865(
        spi=spi,
        rref=config.temperature.rref,
        r0=config.temperature.r0,
        wires=config.temperature.wires,
        filter_frequency=config.temperature.filter_frequency,
    )

    valve = ValveBank(valves)
    meter_optics = MeterOptics(
        ads1115,
        upper_channel=config.ads.meter_upper_channel,
        lower_channel=config.ads.meter_lower_channel,
    )
    digest_optics = DigestOptics(ads1115, channel=config.ads.digest_channel)
    temp_sensor = TemperatureSensor(max31865)

    return HardwareContext(
        valve_io=valve_io,
        control_io=control_io,
        ads1115=ads1115,
        valves=valves,
        optics_controls=optics_controls,
        stepper=stepper,
        pump=pump,
        spi=spi,
        max31865=max31865,
        valve=valve,
        meter_optics=meter_optics,
        digest_optics=digest_optics,
        temp_sensor=temp_sensor,
    )


def cleanup_hardware(ctx: HardwareContext | None) -> None:
    """统一关闭和清理硬件资源。"""

    if not ctx:
        return

    try:
        ctx.valve.close_all()
    except Exception:
        pass

    for pin in ctx.optics_controls.values():
        try:
            pin.close()
        except Exception:
            pass

    for pin in ctx.valves.values():
        try:
            pin.close()
        except Exception:
            pass

    try:
        ctx.ads1115.close()
    except Exception:
        pass

    try:
        ctx.max31865.close()
    except Exception:
        pass

    try:
        ctx.pump.cleanup()
    except Exception:
        pass

    try:
        ctx.valve_io.close()
    except Exception:
        pass

    try:
        ctx.control_io.close()
    except Exception:
        pass


def build_hardware(config: AppConfig | None = None) -> HardwareContext:
    """对外提供统一的硬件构建入口。"""

    return init_hardware(DEFAULT_CONFIG if config is None else config)


def safe_shutdown(ctx: HardwareContext | None) -> None:
    """对外提供统一的安全关闭入口。"""

    cleanup_hardware(ctx)
