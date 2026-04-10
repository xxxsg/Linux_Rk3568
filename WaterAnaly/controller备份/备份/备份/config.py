from __future__ import annotations

import logging
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
    stable_sample_period_ms: int = 20  # 稳定判定时，两次采样之间的间隔
    stable_sample_count: int = 10  # 判定“稳定成立”所需的连续采样次数
    valve_settle_ms: int = 50  # 阀门切换后等待液路稳定的时间
    take_large_timeout_ms: int = 15_000  # 大体积吸液到位超时时间
    take_small_timeout_ms: int = 15_000  # 小体积吸液到位超时时间
    dispense_timeout_ms: int = 10_000  # 排液到空超时时间
    pull_digestor_timeout_ms: int = 12_000  # 从消解器回抽到计量单元的超时时间
    heat_up_timeout_ms: int = 180_000  # 升温到目标温度的最长等待时间
    supplement_blow_ms: int = 500  # 主排液完成后补吹的持续时间
    heat_hold_ms: int = 300_000  # 达到目标温度后的默认保温时长
    heat_poll_ms: int = 500  # 加热阶段的温度轮询周期
    digest_settle_total_ms: int = 900_000  # 消解反应后的总静置时间
    stir_duration_ms: int = 15_000  # 通气搅拌动作持续时间
    optics_warmup_ms: int = 2_000  # 光路切换后等待信号稳定的时间
    clean_pause_ms: int = 20_000  # 清洗阶段每轮之间的额外停顿


@dataclass(frozen=True)
class ThresholdConfig:
    upper_full_mv: float = 1200.0  # 上液位光电阈值，低于该值视为大体积到位
    lower_full_mv: float = 1200.0  # 下液位光电阈值，低于该值视为小体积到位
    empty_mv: float = 2200.0  # 排空阈值，高于该值视为计量单元已空


@dataclass(frozen=True)
class AdsConfig:
    bus: int = 1  # ADS1115 所在 I2C 总线号
    addr: int = 0x48  # ADS1115 的 I2C 地址
    gain: int = ADS1115_REG_CONFIG_PGA_4_096V  # ADS1115 满量程增益配置
    meter_upper_channel: int = 0  # 计量单元上液位检测通道
    meter_lower_channel: int = 1  # 计量单元下液位检测通道
    digest_measure_channel: int = 2  # 消解光学测量通道
    digest_reference_channel: int = 3  # 消解光学参比通道


@dataclass(frozen=True)
class TcaConfig:
    bus: int = 1  # TCA9555 所在 I2C 总线号
    valve_addr: int = 0x20  # 液路阀板扩展 IO 地址
    control_addr: int = 0x21  # 控制板扩展 IO 地址
    valve_pins: dict[str, int] = field(
        default_factory=lambda: {
            "dissolver": 0o0,  # 消解器主液路阀
            "std_1": 0o1,  # 标一/清洗液阀
            "std_2": 0o2,  # 标二/标准液阀
            "sample": 0o3,  # 水样阀
            "analysis_waste": 0o4,  # 分析废液阀
            "reagent_a": 0o5,  # 试剂 A 阀
            "reagent_b": 0o6,  # 试剂 B 阀
            "reagent_c": 0o7,  # 试剂 C 阀
            "clean_waste": 0o10,  # 清洗废液阀
            "dissolver_up": 0o11,  # 消解器上游辅助阀
            "dissolver_down": 0o12,  # 消解器下游辅助阀
        }
    )  # 液路阀门名称到 TCA9555 引脚号的映射
    control_pins: dict[str, int] = field(
        default_factory=lambda: {
            "stepper_dir": 0o0,  # 步进驱动方向控制
            "stepper_ena": 0o1,  # 步进驱动使能控制
            "meter_up": 0o2,  # 计量单元上光电控制/供电
            "meter_down": 0o3,  # 计量单元下光电控制/供电
            "digest_light": 0o4,  # 消解光源控制
            "digest_ref_amp": 0o5,   # 常闭接法，高电平断开
            "digest_main_amp": 0o6,  # 常闭接法，高电平断开
            "digest_heat": 0o7,      # 消解器加热控制
        }
    )  # 控制类执行器到 TCA9555 引脚号的映射


@dataclass(frozen=True)
class PumpConfig:
    
    pulse_pin: tuple[str, int] = ("/dev/gpiochip1", 1)  # 步进脉冲输出引脚
    steps_per_rev: int = 800  # 电机每转对应的细分步数
    rpm: int = 300  # 泵运行转速
    aspirate_direction: str = "forward"  # 吸液时对应的电机方向


@dataclass(frozen=True)
class TemperatureConfig:
    sclk_pin: tuple[str, int] = ("/dev/gpiochip3", 5)  # 软件 SPI 时钟引脚
    mosi_pin: tuple[str, int] = ("/dev/gpiochip1", 0)  # 软件 SPI 主发从收引脚
    miso_pin: tuple[str, int] = ("/dev/gpiochip3", 4)  # 软件 SPI 主收从发引脚
    cs_pin: tuple[str, int] = ("/dev/gpiochip3", 3)  # MAX31865 片选引脚
    rref: float = 430.0  # MAX31865 参考电阻阻值
    r0: float = 100.0  # PT100 在 0 摄氏度时的标称阻值
    wires: int = 2  # RTD 接线方式
    filter_frequency: int = 50  # 工频滤波配置
    heater_hysteresis_c: float = 0.5  # 加热控制回差，避免频繁抖动


@dataclass(frozen=True)
class LoggingConfig:
    """统一日志配置，只通过参数控制，不区分 main/test 逻辑分支。"""

    DEBUG: bool = False  # 是否强制开启调试级别日志
    log_format: str = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"  # 日志输出格式
    date_format: str = "%H:%M:%S"  # 时间字段显示格式


@dataclass(frozen=True)
class RecipeConfig:
    standard_concentration: float = 1.0  # 标液浓度，用于后续标定/校正
    digest_target_temp_c: float = 50.0  # 消解阶段目标温度
    digestor_valves: tuple[str, str, str] = ("dissolver", "dissolver_up", "dissolver_down")  # 消解器液路所需同时打开的阀门组合
    sample_source: str = "sample"  # 水样液源名称
    standard_source: str = "std_2"  # 标液液源名称
    flush_source: str = "std_1"  # 流程冲洗默认液源名称
    clean_source: str = "std_1"  # 收尾清洗默认液源名称
    waste_valve: str = "analysis_waste"  # 默认分析废液出口
    reagent_a_source: str = "reagent_a"  # 试剂 A 液源名称
    reagent_b_source: str = "reagent_b"  # 试剂 B 液源名称
    reagent_c_source: str = "reagent_c"  # 试剂 C 液源名称


@dataclass(frozen=True)
class AnalysisConfig:
    calibration_a: float = 1.0  # 浓度换算公式中的截距参数 a
    calibration_b: float = 1.0  # 浓度换算公式中的斜率参数 b


@dataclass(frozen=True)
class AppConfig:
    timing: TimingConfig = field(default_factory=TimingConfig)  # 时序相关参数集合
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)  # 液位判定阈值集合
    ads: AdsConfig = field(default_factory=AdsConfig)  # ADC 采集配置
    tca: TcaConfig = field(default_factory=TcaConfig)  # IO 扩展与阀门映射配置
    pump: PumpConfig = field(default_factory=PumpConfig)  # 泵与步进驱动配置
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)  # 温度采集与加热控制配置
    logging: LoggingConfig = field(default_factory=LoggingConfig)  # 日志配置
    recipe: RecipeConfig = field(default_factory=RecipeConfig)  # 工艺流程默认配方参数
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)  # 浓度计算参数


def configure_logging(config: AppConfig) -> logging.Logger:
    """按配置统一初始化日志。"""

    if config.logging.DEBUG:
        level = logging.DEBUG
    else:
        level = logging.INFO
    root_logger = logging.getLogger()

    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt=config.logging.log_format,
            datefmt=config.logging.date_format,
        )
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    return root_logger


DEFAULT_CONFIG = AppConfig()
