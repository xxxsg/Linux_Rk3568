from __future__ import annotations

import logging
import math

from config import DEFAULT_CONFIG, configure_logging
from hardware import build_hardware, safe_shutdown
from primitives import (
    DigestSignal,
    add_to_digestor,
    aerate_digestor,
    close_all_valves,
    empty_digestor,
    flush_pipeline,
    heat_and_hold,
    read_digest_signal,
    rinse_to_waste,
    sleep_ms,
)


logger = logging.getLogger(__name__)


def compute_absorbance(signal: DigestSignal) -> float:
    """按双通道公式计算吸光度。"""

    measure_ratio = (signal.vbias_m - signal.vm_0) / (signal.vbias_m - signal.vm_s)
    reference_ratio = (signal.vbias_r - signal.vr_0) / (signal.vbias_r - signal.vr_s)
    ratio = measure_ratio / reference_ratio
    if ratio <= 0:
        raise ValueError(f"invalid absorbance ratio: {ratio}")
    return -math.log10(ratio)


def compute_concentration(signal: DigestSignal, a: float = 1.0, b: float = 1.0) -> float:
    """按公式 `C = (A - a) / b` 计算浓度。"""

    if b == 0:
        raise ValueError("calibration b must not be zero")
    absorbance = compute_absorbance(signal)
    return (absorbance - a) / b


def clean_system(ctx) -> None:
    """执行一轮系统清洗。"""

    recipe = DEFAULT_CONFIG.recipe
    timing = DEFAULT_CONFIG.timing

    logger.info("开始系统清洗")
    add_to_digestor(ctx, recipe.clean_source, "large")
    sleep_ms(timing.clean_pause_ms)
    empty_digestor(ctx, recipe.waste_valve)
    flush_pipeline(ctx, recipe.clean_source, recipe.waste_valve, times=3, volume="large")
    logger.info("系统清洗完成")


def run_water_analysis(ctx, a: float | None = None, b: float | None = None) -> dict[str, float]:
    """执行完整的水质分析流程。"""

    recipe = DEFAULT_CONFIG.recipe
    timing = DEFAULT_CONFIG.timing
    analysis = DEFAULT_CONFIG.analysis
    a = analysis.calibration_a if a is None else a
    b = analysis.calibration_b if b is None else b

    logger.info("开始执行水质分析流程")
    close_all_valves(ctx)

    # 1. 流程开始前先清洗一次系统。
    clean_system(ctx)

    # 2. 依次加入样品和标准液。
    rinse_to_waste(ctx, recipe.sample_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.sample_source, "large")
    rinse_to_waste(ctx, recipe.standard_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.standard_source, "large")

    # 3. 加入试剂 A，并冲洗主通路。
    rinse_to_waste(ctx, recipe.reagent_a_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.reagent_a_source, "large")
    flush_pipeline(ctx, recipe.flush_source, recipe.waste_valve, times=2, volume="large")

    # 4. 进入加热消解阶段。
    heat_and_hold(ctx, target_temp_c=recipe.digest_target_temp_c, hold_ms=timing.heat_hold_ms)

    # 5. 加入试剂 B。
    rinse_to_waste(ctx, recipe.reagent_b_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.reagent_b_source, "large")
    flush_pipeline(ctx, recipe.flush_source, recipe.waste_valve, times=1, volume="large")

    # 6. 静置反应，中途通气搅拌一次。
    sleep_ms(timing.digest_settle_total_ms / 2)
    aerate_digestor(ctx, timing.stir_duration_ms)
    sleep_ms(timing.digest_settle_total_ms / 2)

    # 7. 加入试剂 C，准备最终读数。
    rinse_to_waste(ctx, recipe.reagent_c_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.reagent_c_source, "large")
    flush_pipeline(ctx, recipe.flush_source, recipe.waste_valve, times=2, volume="large")

    # 8. 读取 6 个电压并计算结果。
    signal = read_digest_signal(ctx)
    logger.info(
        "消解读数完成: vbias_m=%.6f vbias_r=%.6f vm_0=%.6f vr_0=%.6f vm_s=%.6f vr_s=%.6f",
        signal.vbias_m,
        signal.vbias_r,
        signal.vm_0,
        signal.vr_0,
        signal.vm_s,
        signal.vr_s,
    )
    absorbance = compute_absorbance(signal)
    concentration = compute_concentration(signal, a=a, b=b)

    # 9. 排空并再次清洗，恢复安全状态。
    empty_digestor(ctx, recipe.waste_valve)
    clean_system(ctx)
    close_all_valves(ctx)

    logger.info("水质分析流程结束: absorbance=%.6f concentration=%.6f", absorbance, concentration)
    return {
        "vbias_m": signal.vbias_m,
        "vbias_r": signal.vbias_r,
        "vm_0": signal.vm_0,
        "vr_0": signal.vr_0,
        "vm_s": signal.vm_s,
        "vr_s": signal.vr_s,
        "absorbance": absorbance,
        "concentration": concentration,
    }


def main() -> None:
    """程序主入口。"""

    ctx = None
    configure_logging(DEFAULT_CONFIG)
    try:
        ctx = build_hardware(DEFAULT_CONFIG)
        result = run_water_analysis(
            ctx,
            a=DEFAULT_CONFIG.analysis.calibration_a,
            b=DEFAULT_CONFIG.analysis.calibration_b,
        )
        logger.info("最终结果 absorbance=%.6f", result["absorbance"])
        logger.info("最终结果 concentration=%.6f", result["concentration"])
    except Exception:
        logger.exception("主流程执行失败")
        raise
    finally:
        safe_shutdown(ctx)


if __name__ == "__main__":
    main()
