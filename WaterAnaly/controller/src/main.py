from __future__ import annotations

from config import DEFAULT_CONFIG
from hardware import build_hardware, safe_shutdown
from primitives import (
    add_to_digestor,
    aerate_digestor,
    compute_concentration,
    empty_digestor,
    flush_pipeline,
    heat_and_hold,
    read_digest_value,
    rinse_to_waste,
    sleep_ms,
)


def clean_system(hw) -> None:
    """开机或收尾时的基础清洗流程。"""

    recipe = DEFAULT_CONFIG.recipe
    timing = DEFAULT_CONFIG.timing

    add_to_digestor(hw, recipe.clean_source, "large")
    sleep_ms(timing.clean_pause_ms)
    empty_digestor(hw, recipe.waste_valve)
    flush_pipeline(hw, recipe.clean_source, recipe.waste_valve, times=3, volume="large")


def run_water_analysis(hw, standard_concentration: float | None = None) -> dict[str, float]:
    """按 readme 里的工艺顺序执行整套水分析流程。"""

    recipe = DEFAULT_CONFIG.recipe
    timing = DEFAULT_CONFIG.timing
    standard_concentration = (
        recipe.standard_concentration if standard_concentration is None else standard_concentration
    )

    # 先做一次总复位，避免继承上一次流程状态。
    for pin in hw["valves"].values():
        pin.write(False)

    # 0) 开机清洗
    clean_system(hw)

    # 1) 样品：润洗 + 正式加样
    rinse_to_waste(hw, recipe.sample_source, recipe.waste_valve)
    add_to_digestor(hw, recipe.sample_source, "large")

    # 2) 标液：润洗 + 正式加样
    rinse_to_waste(hw, recipe.standard_source, recipe.waste_valve)
    add_to_digestor(hw, recipe.standard_source, "large")

    # 3) 试剂 A：加入后再用标液冲洗管路
    rinse_to_waste(hw, recipe.reagent_a_source, recipe.waste_valve)
    add_to_digestor(hw, recipe.reagent_a_source, "large")
    flush_pipeline(hw, recipe.flush_source, recipe.waste_valve, times=2, volume="large")

    # 4) 升温并保持
    heat_and_hold(hw, target_temp_c=recipe.digest_target_temp_c, hold_ms=timing.heat_hold_ms)

    # 5) 试剂 B：加入后做一次冲洗
    rinse_to_waste(hw, recipe.reagent_b_source, recipe.waste_valve)
    add_to_digestor(hw, recipe.reagent_b_source, "large")
    flush_pipeline(hw, recipe.flush_source, recipe.waste_valve, times=1, volume="large")

    # 6) 静置过程中间执行一次通气搅拌
    sleep_ms(timing.digest_settle_total_ms / 2)
    aerate_digestor(hw, timing.stir_duration_ms)
    sleep_ms(timing.digest_settle_total_ms / 2)

    # 7) 试剂 C：加入后再冲洗
    rinse_to_waste(hw, recipe.reagent_c_source, recipe.waste_valve)
    add_to_digestor(hw, recipe.reagent_c_source, "large")
    flush_pipeline(hw, recipe.flush_source, recipe.waste_valve, times=2, volume="large")

    # 8) 读吸光度，9) 换算浓度
    absorbance = read_digest_value(hw)
    concentration = compute_concentration(absorbance, standard_concentration)

    # 10) 排空并做收尾清洗
    empty_digestor(hw, recipe.waste_valve)
    clean_system(hw)
    for pin in hw["valves"].values():
        pin.write(False)

    return {
        "absorbance": absorbance,
        "concentration": concentration,
    }


def main() -> None:
    """脚本入口：初始化硬件，执行流程，并统一做安全收尾。"""

    hw = None
    try:
        hw = build_hardware(DEFAULT_CONFIG)
        result = run_water_analysis(hw, standard_concentration=DEFAULT_CONFIG.recipe.standard_concentration)
        print(f"[RESULT] absorbance={result['absorbance']:.2f}")
        print(f"[RESULT] concentration={result['concentration']:.2f}")
    finally:
        safe_shutdown(hw)


if __name__ == "__main__":
    main()
