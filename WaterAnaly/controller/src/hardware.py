from __future__ import annotations

import os
import sys
import time

from dataclasses import dataclass
from typing import TYPE_CHECKING


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

if TYPE_CHECKING:
    from lib.TCA9555 import TCA9555


VALVE_PIN_ORDER = list(DEFAULT_CONFIG.tca.valve_pins.items())

# 光学与加热相关控制脚，保留固定顺序便于统一初始化和排查。
OPTICS_CTRL_PIN_ORDER = [
    ("meter_up", DEFAULT_CONFIG.tca.control_pins["meter_up"]),
    ("meter_down", DEFAULT_CONFIG.tca.control_pins["meter_down"]),
    ("digest_light", DEFAULT_CONFIG.tca.control_pins["digest_light"]),
    ("digest_ref_amp", DEFAULT_CONFIG.tca.control_pins["digest_ref_amp"]),
    ("digest_main_amp", DEFAULT_CONFIG.tca.control_pins["digest_main_amp"]),
    ("digest_heat", DEFAULT_CONFIG.tca.control_pins["digest_heat"]),
]


class ValveBank:
    """液路阀门集合封装，通过批量 I2C 写入优化阀门操作。"""

    def __init__(
        self,
        tca: "TCA9555",
        pin_map: dict[str, int],
        i2c_settle_ms: int = 5,
    ) -> None:
        self._tca = tca
        self._pin_map = pin_map
        self._i2c_settle_ms = i2c_settle_ms

        self._pin_to_port: dict[str, int] = {}
        self._pin_to_bit: dict[str, int] = {}
        for name, pin_no in pin_map.items():
            port = pin_no // 8
            bit = pin_no % 8
            self._pin_to_port[name] = port
            self._pin_to_bit[name] = bit

    def _get_current_output(self) -> int:
        return self._tca.read_word(source="output")

    def _calculate_port_values(self, pin_names: list[str], value: bool) -> tuple[int | None, int | None]:
        port0_value = None
        port1_value = None

        current = self._get_current_output()

        for name in pin_names:
            port = self._pin_to_port[name]
            bit = self._pin_to_bit[name]
            if port == 0:
                if value:
                    port0_value = (port0_value if port0_value is not None else (current & 0xFF)) | (1 << bit)
                else:
                    port0_value = (port0_value if port0_value is not None else (current & 0xFF)) & ~(1 << bit)
            else:
                if value:
                    port1_value = (port1_value if port1_value is not None else ((current >> 8) & 0xFF)) | (1 << bit)
                else:
                    port1_value = (port1_value if port1_value is not None else ((current >> 8) & 0xFF)) & ~(1 << bit)

        return port0_value, port1_value

    def close_all(self) -> None:
        self._tca.write_word(0)
        time.sleep(self._i2c_settle_ms / 1000.0)

    def open(self, names: list[str] | tuple[str, ...]) -> None:
        names = list(names)
        port0_value, port1_value = self._calculate_port_values(names, True)

        if port0_value is not None and port1_value is not None:
            new_value = port0_value | (port1_value << 8)
            self._tca.write_word(new_value)
        elif port0_value is not None:
            self._tca.write_port(0, port0_value)
        elif port1_value is not None:
            self._tca.write_port(1, port1_value)

        time.sleep(self._i2c_settle_ms / 1000.0)


class MeterOptics:
    """计量单元液位光电读取封装。"""

    def __init__(
        self,
        ads: ADS1115,
        upper_channel: int,
        lower_channel: int,
        upper_control_pin: Tca9555Pin,
        lower_control_pin: Tca9555Pin,
    ) -> None:
        self._ads = ads
        self._upper_channel = upper_channel
        self._lower_channel = lower_channel
        self._upper_pin = upper_control_pin
        self._lower_pin = lower_control_pin

    def read_upper_mv(self) -> float:
        return float(self._ads.read_voltage(self._upper_channel))

    def read_lower_mv(self) -> float:
        return float(self._ads.read_voltage(self._lower_channel))

    def light_on(self) -> None:
        self._upper_pin.write(True)
        self._lower_pin.write(True)

    def light_off(self) -> None:
        self._upper_pin.write(False)
        self._lower_pin.write(False)


class DigestOptics:
    """消解器读数光路封装，统一管理光源和两路放大通道。"""

    def __init__(
        self,
        ads: ADS1115,
        measure_channel: int,
        reference_channel: int,
        light_pin: Tca9555Pin,
        ref_amp_pin: Tca9555Pin,
        main_amp_pin: Tca9555Pin,
    ) -> None:
        self._ads = ads
        self._measure_channel = measure_channel
        self._reference_channel = reference_channel
        self._light_pin = light_pin
        self._ref_amp_pin = ref_amp_pin
        self._main_amp_pin = main_amp_pin

    def read_measure_mv(self) -> float:
        return float(self._ads.read_voltage(self._measure_channel))

    def read_reference_mv(self) -> float:
        return float(self._ads.read_voltage(self._reference_channel))

    def light_on(self) -> None:
        self._light_pin.write(True)

    def light_off(self) -> None:
        self._light_pin.write(False)

    def connect_paths(self) -> None:
        # 低电平闭合模拟通道，接入测量链路。
        self._ref_amp_pin.write(False)
        self._main_amp_pin.write(False)

    def disconnect_paths(self) -> None:
        # 高电平断开模拟通道，读取偏置本底。
        self._ref_amp_pin.write(True)
        self._main_amp_pin.write(True)


class HeaterControl:
    """消解器加热开关封装。"""

    def __init__(self, pin: Tca9555Pin) -> None:
        self._pin = pin

    def on(self) -> None:
        self._pin.write(True)

    def off(self) -> None:
        self._pin.write(False)


class TemperatureSensor:
    """温度传感器读取封装。"""

    def __init__(self, probe: MAX31865) -> None:
        self._probe = probe

    def read_temperature_c(self) -> float:
        return float(self._probe.read_temperature())


@dataclass(frozen=True)
class HardwareContext:
    """集中持有整套硬件对象，供流程层与元语层复用。"""

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
    heater: HeaterControl
    temp_sensor: TemperatureSensor


def _build_tca_pins(io: TCA9555, pin_map: dict[str, int]) -> dict[str, Tca9555Pin]:
    """按名称批量创建 TCA9555 引脚对象。"""

    pins: dict[str, Tca9555Pin] = {}
    for name, pin_no in pin_map.items():
        pins[name] = Tca9555Pin(io, pin_no, initial_value=False)
    return pins


def init_hardware(config: AppConfig = DEFAULT_CONFIG) -> HardwareContext:
    """完成底层驱动、引脚对象和上层硬件封装的整套初始化。"""

    # 1. 初始化 I2C 设备。
    valve_io = TCA9555(i2c_bus=config.tca.bus, addr=config.tca.valve_addr)
    control_io = TCA9555(i2c_bus=config.tca.bus, addr=config.tca.control_addr)
    ads1115 = ADS1115(i2c_bus=config.ads.bus, addr=config.ads.addr)
    ads1115.set_gain(config.ads.gain)

    # 2. 构建阀门与控制脚抽象。
    valves = _build_tca_pins(valve_io, config.tca.valve_pins)
    optics_controls = _build_tca_pins(
        control_io,
        {
            "meter_up": config.tca.control_pins["meter_up"],
            "meter_down": config.tca.control_pins["meter_down"],
            "digest_light": config.tca.control_pins["digest_light"],
            "digest_ref_amp": config.tca.control_pins["digest_ref_amp"],
            "digest_main_amp": config.tca.control_pins["digest_main_amp"],
            "digest_heat": config.tca.control_pins["digest_heat"],
        },
    )
    max31865_cs = Tca9555Pin(
        control_io,
        config.tca.control_pins["max31865_cs"],
        initial_value=True,
    )

    # 3. 构建泵驱动所需的步进电机控制对象。
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

    stepper = Stepper(
        pul_pin=pul_pin,
        dir_pin=dir_pin,
        steps_per_rev=config.pump.steps_per_rev,
    )
    stepper.configure_driver(
        dir_high_forward=True,
    )
    stepper.set_rpm(config.pump.rpm)

    pump = Pump(driver=stepper, aspirate_direction=config.pump.aspirate_direction)

    # 4. 构建温度采集链路。
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
        cs=max31865_cs,
    )
    max31865 = MAX31865(
        spi=spi,
        rref=config.temperature.rref,
        r0=config.temperature.r0,
        wires=config.temperature.wires,
        filter_frequency=config.temperature.filter_frequency,
    )

    # 5. 构建流程层实际使用的高层硬件对象。
    valve = ValveBank(valve_io, config.tca.valve_pins)
    meter_optics = MeterOptics(
        ads1115,
        upper_channel=config.ads.meter_upper_channel,
        lower_channel=config.ads.meter_lower_channel,
        upper_control_pin=optics_controls["meter_up"],
        lower_control_pin=optics_controls["meter_down"],
    )
    digest_optics = DigestOptics(
        ads1115,
        measure_channel=config.ads.digest_measure_channel,
        reference_channel=config.ads.digest_reference_channel,
        light_pin=optics_controls["digest_light"],
        ref_amp_pin=optics_controls["digest_ref_amp"],
        main_amp_pin=optics_controls["digest_main_amp"],
    )
    heater = HeaterControl(optics_controls["digest_heat"])
    temp_sensor = TemperatureSensor(max31865)

    # 6. 汇总成统一上下文，便于主流程传递。
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
        heater=heater,
        temp_sensor=temp_sensor,
    )


def cleanup_hardware(ctx: HardwareContext | None) -> None:
    """按安全优先顺序尽量关闭所有硬件资源。"""

    if not ctx:
        return

    try:
        # 先关加热，避免收尾过程中继续升温。
        ctx.heater.off()
    except Exception:
        pass

    try:
        # 再关闭全部阀门，恢复液路安全态。
        ctx.valve.close_all()
    except Exception:
        pass

    # 引脚对象逐个释放，即使局部失败也继续执行后续清理。
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
    """对外暴露的硬件构建入口。"""

    return init_hardware(DEFAULT_CONFIG if config is None else config)


def safe_shutdown(ctx: HardwareContext | None) -> None:
    """对外暴露的安全关机入口。"""

    cleanup_hardware(ctx)
