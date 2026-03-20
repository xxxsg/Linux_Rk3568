from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


# 允许直接从 `src` 目录运行脚本时导入上一级 `lib`。
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V


# 与底层 Stepper / Pump 约定保持一致的方向常量。
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
    """计量单元满位 / 空位判定阈值。"""

    upper_full_mv: float = 1200.0
    lower_full_mv: float = 1200.0
    empty_mv: float = 2200.0


@dataclass(frozen=True)
class AdsConfig:
    """ADS1115 及各通道功能分配。"""

    bus: int = 1
    addr: int = 0x48
    gain: int = ADS1115_REG_CONFIG_PGA_4_096V
    meter_upper_channel: int = 0
    meter_lower_channel: int = 1
    digest_channel: int = 2


@dataclass(frozen=True)
class TcaConfig:
    """TCA9555 的 I2C 参数。"""

    bus: int = 1
    addr: int = 0x20


@dataclass(frozen=True)
class PumpConfig:
    """步进泵相关的引脚和运行参数。"""

    pulse_pin: tuple[str, int] = ("/dev/gpiochip1", 1)
    direction_pin: int = 14
    enable_pin: int = 15
    steps_per_rev: int = 800
    rpm: int = 300
    aspirate_direction: str = "reverse"


@dataclass(frozen=True)
class TemperatureConfig:
    """MAX31865 软 SPI 接线及传感器参数。"""

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
    """工艺流程中用到的液路命名和默认参数。"""

    standard_concentration: float = 1.0
    digest_target_temp_c: float = 50.0
    # 计量单元为常开，不单独配置入口阀。
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
    """统一配置入口，供硬件装配和流程调用。"""

    timing: TimingConfig = field(default_factory=TimingConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    ads: AdsConfig = field(default_factory=AdsConfig)
    tca: TcaConfig = field(default_factory=TcaConfig)
    pump: PumpConfig = field(default_factory=PumpConfig)
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)
    recipe: RecipeConfig = field(default_factory=RecipeConfig)
    valve_pin_map: dict[str, int] = field(
        default_factory=lambda: {
            "dissolver": 0,
            "std_1": 1,
            "std_2": 2,
            "sample": 3,
            "analysis_waste": 4,
            "reagent_a": 5,
            "reagent_b": 6,
            "reagent_c": 7,
            "clean_waste": 8,
            "dissolver_up": 9,
            "dissolver_down": 10,
        }
    )


# 默认配置用于 main 直接运行，也方便测试时按需覆盖。
DEFAULT_CONFIG = AppConfig()
