from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V


DIR_FORWARD = "FORWARD"
DIR_REVERSE = "REVERSE"


@dataclass(frozen=True)
class TimingConfig:
    """流程中的时间参数。"""

    stable_sample_period_ms: int = 20
    stable_sample_count: int = 10
    valve_settle_ms: int = 50
    take_large_timeout_ms: int = 15_000
    take_small_timeout_ms: int = 15_000
    dispense_timeout_ms: int = 10_000
    pull_digestor_timeout_ms: int = 12_000
    heat_up_timeout_ms: int = 180_000
    supplement_blow_ms: int = 500
    heat_hold_ms: int = 300_000
    digest_settle_total_ms: int = 900_000
    stir_duration_ms: int = 15_000
    optics_warmup_ms: int = 2_000
    clean_pause_ms: int = 20_000


@dataclass(frozen=True)
class ThresholdConfig:
    """计量单元液位判断阈值，单位 mV。"""

    upper_full_mv: float = 1200.0
    lower_full_mv: float = 1200.0
    empty_mv: float = 2200.0


@dataclass(frozen=True)
class AdsConfig:
    """ADS1115 采集配置。"""

    bus: int = 1
    addr: int = 0x48
    gain: int = ADS1115_REG_CONFIG_PGA_4_096V
    meter_upper_channel: int = 0
    meter_lower_channel: int = 1
    digest_channel: int = 2


@dataclass(frozen=True)
class TcaConfig:
    """TCA9555 配置。

    - `valve_pins` 是液路阀所在的扩展 IO 编号
    - `control_pins` 是控制类输出所在的扩展 IO 编号

    这里统一使用八进制表示 TCA9555 的 pin，方便和硬件丝印/历史文档保持一致。
    """

    bus: int = 1
    valve_addr: int = 0x20
    control_addr: int = 0x21
    valve_pins: dict[str, int] = field(
        default_factory=lambda: {
            "dissolver": 0o0,  # 消解器主阀
            "std_1": 0o1,  # 标一/清洗液阀
            "std_2": 0o2,  # 标二阀
            "sample": 0o3,  # 水样阀
            "analysis_waste": 0o4,  # 分析废液阀
            "reagent_a": 0o5,  # 试剂 A 阀
            "reagent_b": 0o6,  # 试剂 B 阀
            "reagent_c": 0o7,  # 试剂 C 阀
            "clean_waste": 0o10,  # 清洗废液阀
            "dissolver_up": 0o11,  # 消解器上通路阀
            "dissolver_down": 0o12,  # 消解器下通路阀
        }
    )
    control_pins: dict[str, int] = field(
        default_factory=lambda: {
            "stepper_dir": 0o0,  # 泵电机方向控制
            "stepper_ena": 0o1,  # 泵电机使能控制
            "meter_up": 0o2,  # 计量单元上液位光路控制
            "meter_down": 0o3,  # 计量单元下液位光路控制
            "digest_light": 0o4,  # 消解器读数光源控制
            "digest_ref_amp": 0o5,  # 消解器参考通道控制
            "digest_main_amp": 0o6,  # 消解器测量通道控制
        }
    )


@dataclass(frozen=True)
class PumpConfig:
    """泵和步进电机相关配置。"""

    pulse_pin: tuple[str, int] = ("/dev/gpiochip1", 1)
    steps_per_rev: int = 800
    rpm: int = 300
    aspirate_direction: str = "reverse"


@dataclass(frozen=True)
class TemperatureConfig:
    """MAX31865 与温度探头配置。"""

    sclk_pin: tuple[str, int] = ("/dev/gpiochip3", 5)
    mosi_pin: tuple[str, int] = ("/dev/gpiochip1", 0)
    miso_pin: tuple[str, int] = ("/dev/gpiochip3", 4)
    cs_pin: tuple[str, int] = ("/dev/gpiochip3", 3)
    rref: float = 430.0
    r0: float = 100.0
    wires: int = 2
    filter_frequency: int = 50


@dataclass(frozen=True)
class RecipeConfig:
    """主流程使用的液路命名和默认工艺参数。"""

    standard_concentration: float = 1.0
    digest_target_temp_c: float = 50.0
    digestor_valves: tuple[str, str, str] = ("dissolver", "dissolver_up", "dissolver_down")
    sample_source: str = "sample"
    standard_source: str = "std_2"
    flush_source: str = "std_1"
    clean_source: str = "std_1"
    waste_valve: str = "analysis_waste"
    reagent_a_source: str = "reagent_a"
    reagent_b_source: str = "reagent_b"
    reagent_c_source: str = "reagent_c"


@dataclass(frozen=True)
class AppConfig:
    """统一配置入口。

    原则上：
    - 会调的东西放这里
    - `hardware.py` 只按这里的配置完成装配
    """

    timing: TimingConfig = field(default_factory=TimingConfig)  # 流程时序参数
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)  # 液位判断阈值
    ads: AdsConfig = field(default_factory=AdsConfig)  # ADS1115 采集配置
    tca: TcaConfig = field(default_factory=TcaConfig)  # TCA9555 地址和 pin 映射
    pump: PumpConfig = field(default_factory=PumpConfig)  # 泵和步进电机参数
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)  # 温度采集配置
    recipe: RecipeConfig = field(default_factory=RecipeConfig)  # 主流程工艺参数


DEFAULT_CONFIG = AppConfig()
