"""Hardware layer based on CircuitPython drivers."""

from dataclasses import dataclass
import time
from typing import Any, Dict, Optional

import board
import busio
import digitalio

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_max31865
import adafruit_tca9555

import config as cfg
from config import *


def _get_board_pin(pin_name: str):
    """把字符串形式的引脚名（如 'D5'）转换成 board 模块里的引脚对象。"""
    try:
        return getattr(board, pin_name)
    except AttributeError as exc:
        raise ValueError(f"board pin not found: {pin_name!r}") from exc


class TCA9555Driver:
    """TCA9555 IO 扩展芯片封装。

    作用：通过 I2C 扩展数字输出口，用来控制阀门/步进驱动器等开关量。
    """

    def __init__(self, i2c, addr):
        self.chip = adafruit_tca9555.TCA9555(i2c, address=addr)
        # 缓存已初始化的 pin，避免重复 get_pin/switch_to_output
        self._pins: Dict[int, Any] = {}
        # 记录 16 位输出状态，便于调试查看当前所有 IO 电平
        self.state = 0x0000

    def _get_pin(self, pin_no):
        # 第一次访问某个 pin 时，初始化为输出且默认低电平
        if pin_no not in self._pins:
            pin = self.chip.get_pin(pin_no)
            pin.switch_to_output(value=False)
            self._pins[pin_no] = pin
        return self._pins[pin_no]

    def write_pin(self, pin_no, high):
        # 写入单个输出引脚，并同步更新状态位图
        pin = self._get_pin(pin_no)
        pin.value = bool(high)
        if high:
            self.state |= 1 << pin_no
        else:
            self.state &= ~(1 << pin_no)


class ADS1115Driver:
    """ADS1115 模拟采集芯片封装。

    读取指定通道电压并统一返回毫伏值（mV）。
    """

    _CHANNEL_MAP = {
        0: ADS.P0,
        1: ADS.P1,
        2: ADS.P2,
        3: ADS.P3,
    }

    def __init__(self, i2c, addr):
        self.ads = ADS.ADS1115(i2c, address=addr)
        # gain=1 对应较常用的输入量程，满足大多数电压采集需求
        self.ads.gain = 1
        # 预创建 0~3 通道对象，后续读取更直接
        self._channels = {
            idx: AnalogIn(self.ads, channel)
            for idx, channel in self._CHANNEL_MAP.items()
        }

    def read_channel_mv(self, channel):
        # 统一单位：V -> mV，方便上层算法直接使用
        if channel not in self._channels:
            raise ValueError(f"unsupported ADS1115 channel: {channel}")
        return self._channels[channel].voltage * 1000.0


class MAX31865Driver:
    """MAX31865 温度采集封装（RTD/PT100 等）。"""

    def __init__(
        self,
        spi,
        cs_pin_name: str,
        *,
        wires: int = 2,
        rtd_nominal: float = 100.0,
        ref_resistor: float = 430.0,
    ):
        # CS 片选引脚来自配置文件（默认 D5）
        self.cs = digitalio.DigitalInOut(_get_board_pin(cs_pin_name))
        self.sensor = adafruit_max31865.MAX31865(
            spi,
            self.cs,
            wires=wires,
            rtd_nominal=rtd_nominal,
            ref_resistor=ref_resistor,
        )

    def read_temperature(self):
        return self.sensor.temperature

    def deinit(self):
        self.cs.deinit()


class ValveCtrl:
    """阀门控制器：把阀门名字映射到 TCA9555 的具体 pin。"""

    def __init__(self, tca_driver, valve_pin_map):
        self.tca = tca_driver
        self.valve_pin_map = valve_pin_map

    def open(self, valve_names):
        # 兼容传入单个名称或名称列表
        names = valve_names if isinstance(valve_names, list) else [valve_names]
        for name in names:
            self.tca.write_pin(self.valve_pin_map[name], True)

    def close(self, valve_names):
        names = valve_names if isinstance(valve_names, list) else [valve_names]
        for name in names:
            self.tca.write_pin(self.valve_pin_map[name], False)

    def close_all(self):
        for _, pin in self.valve_pin_map.items():
            self.tca.write_pin(pin, False)


class StepperPump:
    """PUL/DIR/ENA pump wrapper for external stepper driver."""

    def __init__(self, tca_driver, pul_pin, dir_pin, ena_pin, subdivision, rpm):
        self.tca = tca_driver
        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin
        self.subdivision = subdivision
        self.rpm = rpm
        # 一个脉冲周期=高电平半周期+低电平半周期，单位秒
        # 30/(rpm*subdivision) 推导自 60 秒/分钟 和“每周期两个 half period”
        self.half_period = 30.0 / (self.rpm * self.subdivision)
        # 默认正转
        self.direction = DIR_FORWARD

        # 上电初始化：脉冲脚拉低、方向脚默认、使能脚默认关闭电机
        self.tca.write_pin(self.pul_pin, False)
        self.tca.write_pin(self.dir_pin, False)
        self.tca.write_pin(self.ena_pin, True)

    def set_direction(self, direction):
        if direction not in (DIR_FORWARD, DIR_REVERSE):
            raise ValueError(f"unsupported pump direction: {direction}")
        self.direction = direction
        self.tca.write_pin(self.dir_pin, direction == DIR_FORWARD)

    def enable(self):
        # 常见步进驱动器 ENA 为低有效：False 表示使能
        self.tca.write_pin(self.ena_pin, False)

    def disable(self):
        # True 表示失能，停止输出
        self.tca.write_pin(self.ena_pin, True)

    def pulse(self):
        self.tca.write_pin(self.pul_pin, True)
        time.sleep(self.half_period)
        self.tca.write_pin(self.pul_pin, False)
        time.sleep(self.half_period)

    def run_for(self, duration_ms):
        # 在指定时长内持续输出脉冲
        end_at = time.time() + duration_ms / 1000.0
        while time.time() < end_at:
            self.pulse()


class MeterOptics:
    """比色计光学读数封装（上/下通道透过率）。"""

    def __init__(self, ads_driver):
        self.ads = ads_driver

    def read_upper_transmittance(self):
        return self.ads.read_channel_mv(METER_UPPER_CHANNEL)

    def read_lower_transmittance(self):
        return self.ads.read_channel_mv(METER_LOWER_CHANNEL)


class DigestOptics:
    """消解模块光学读数封装（吸光度通道）。"""

    def __init__(self, ads_driver):
        self.ads = ads_driver

    def read_absorbance(self):
        return self.ads.read_channel_mv(DIGEST_OPTICS_CHANNEL)


class TempController:
    """温控流程封装。

    注意：当前仅保存目标温度和读温/延时逻辑，未直接实现 PID 或加热开关控制。
    """

    def __init__(self, sensor_driver):
        self.sensor = sensor_driver
        self.target_temp = 0.0

    def start(self, target_temp):
        self.target_temp = target_temp

    def read_temperature(self):
        return self.sensor.read_temperature()

    def hold(self, hold_ms):
        time.sleep(hold_ms / 1000.0)

    def stop(self):
        self.target_temp = 0.0


@dataclass
class HardwareContext:
    """硬件对象集合，统一交给上层业务使用。"""

    bus: Any
    valve: ValveCtrl
    pump: StepperPump
    meter_optics: MeterOptics
    temp_ctrl: TempController
    digest_optics: DigestOptics
    spi: Optional[Any] = None
    temp_sensor: Optional[MAX31865Driver] = None

    def shutdown(self):
        # 统一下电/释放资源，防止退出时硬件仍处于工作状态
        self.pump.disable()
        self.valve.close_all()
        if self.temp_sensor is not None:
            self.temp_sensor.deinit()
        if self.spi is not None and hasattr(self.spi, "deinit"):
            self.spi.deinit()
        if self.bus is not None and hasattr(self.bus, "deinit"):
            self.bus.deinit()


def create_hardware_context():
    """创建并返回硬件上下文对象。

    包含：
    - I2C 总线 + TCA9555 + ADS1115
    - SPI 总线 + MAX31865 温度传感器
    - 业务层控制对象（阀门、泵、光学、温控）
    """
    i2c = busio.I2C(board.SCL, board.SDA)
    tca = TCA9555Driver(i2c, TCA9555_I2C_ADDR)
    ads = ADS1115Driver(i2c, ADS1115_I2C_ADDR)

    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    temp_sensor = MAX31865Driver(
        spi,
        getattr(cfg, "MAX31865_CS_PIN", "D5"),
        wires=getattr(cfg, "MAX31865_WIRES", 2),
        rtd_nominal=getattr(cfg, "MAX31865_RTD_NOMINAL", 100.0),
        ref_resistor=getattr(cfg, "MAX31865_REF_RESISTOR", 430.0),
    )

    return HardwareContext(
        bus=i2c,
        valve=ValveCtrl(tca, VALVE_PIN_MAP),
        pump=StepperPump(
            tca,
            pul_pin=PUMP_PUL_PIN,
            dir_pin=PUMP_DIR_PIN,
            ena_pin=PUMP_ENA_PIN,
            subdivision=PUMP_SUBDIVISION,
            rpm=PUMP_TARGET_RPM,
        ),
        meter_optics=MeterOptics(ads),
        temp_ctrl=TempController(temp_sensor),
        digest_optics=DigestOptics(ads),
        spi=spi,
        temp_sensor=temp_sensor,
    )
