from __future__ import annotations

from config import DEFAULT_CONFIG
from hardware import build_hardware, safe_shutdown
from primitives import (
    add_to_digestor,
    aerate_digestor,
    close_all_valves,
    empty_digestor,
    flush_pipeline,
    heat_and_hold,
    read_digest_value,
    rinse_to_waste,
    sleep_ms,
)


def compute_concentration(absorbance: float, standard_concentration: float) -> float:
    """把读数结果换算为浓度。

    这里先保留当前项目使用的简化线性算法，
    让主流程先有一个稳定的结果出口。

    如果后面要接入 `Agent.md` 里的正式吸光度公式，
    优先改这个函数，不要把公式散落到主流程步骤里。
    """

    return absorbance * standard_concentration


def clean_system(ctx) -> None:
    """执行一次基础系统清洗。

    这个动作会在两个阶段复用：
    - 开机后先清洗一次，把系统带到可分析的起始状态
    - 全流程结束后再清洗一次，作为收尾

    清洗步骤本身很简单：
    1. 把清洗液送入消解器
    2. 停留一段时间，让液体覆盖关键液路
    3. 把消解器排空
    4. 再对主管路做几轮冲洗
    """

    recipe = DEFAULT_CONFIG.recipe
    timing = DEFAULT_CONFIG.timing

    add_to_digestor(ctx, recipe.clean_source, "large")
    sleep_ms(timing.clean_pause_ms)
    empty_digestor(ctx, recipe.waste_valve)
    flush_pipeline(ctx, recipe.clean_source, recipe.waste_valve, times=3, volume="large")


def run_water_analysis(ctx, standard_concentration: float | None = None) -> dict[str, float]:
    """按项目定义的主工艺顺序完成一次完整分析。

    这个函数是流程层入口，负责把各个基础动作串成一条完整工艺链。
    它只关心两类事情：
    - 步骤顺序是否符合工艺定义
    - 结束时是否安全收尾并返回结果

    它不应该直接处理底层 pin、ADC 通道号或电机方向，
    这些细节都应该留在 `hardware.py` 和 `primitives.py` 中。
    """

    recipe = DEFAULT_CONFIG.recipe
    timing = DEFAULT_CONFIG.timing
    standard_concentration = (
        recipe.standard_concentration if standard_concentration is None else standard_concentration
    )

    # 先统一关阀，避免继承上一次运行遗留的液路状态。
    close_all_valves(ctx)

    # 0) 开机清洗：先把整个系统带到一个较干净、较稳定的起点。
    clean_system(ctx)

    # 1) 水样流程：先小体积润洗支路，再正式把水样送入消解器。
    rinse_to_waste(ctx, recipe.sample_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.sample_source, "large")

    # 2) 标液流程：和水样一样，先润洗再正式加入。
    rinse_to_waste(ctx, recipe.standard_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.standard_source, "large")

    # 3) 试剂 A：加完后额外做冲洗，尽量减少残液挂壁和交叉污染。
    rinse_to_waste(ctx, recipe.reagent_a_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.reagent_a_source, "large")
    flush_pipeline(ctx, recipe.flush_source, recipe.waste_valve, times=2, volume="large")

    # 4) 升温保温：等待消解器达到目标温度，并保持足够的反应时间。
    heat_and_hold(ctx, target_temp_c=recipe.digest_target_temp_c, hold_ms=timing.heat_hold_ms)

    # 5) 试剂 B：继续按“润洗 -> 加入 -> 冲洗”的模式执行。
    rinse_to_waste(ctx, recipe.reagent_b_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.reagent_b_source, "large")
    flush_pipeline(ctx, recipe.flush_source, recipe.waste_valve, times=1, volume="large")

    # 6) 静置反应：拆成前后两段，中间穿插一次通气搅拌。
    # 这样既保留静置时间，也给反应体系一次重新混匀的机会。
    sleep_ms(timing.digest_settle_total_ms / 2)
    aerate_digestor(ctx, timing.stir_duration_ms)
    sleep_ms(timing.digest_settle_total_ms / 2)

    # 7) 试剂 C：最后一轮加药，做法和前面保持一致。
    rinse_to_waste(ctx, recipe.reagent_c_source, recipe.waste_valve)
    add_to_digestor(ctx, recipe.reagent_c_source, "large")
    flush_pipeline(ctx, recipe.flush_source, recipe.waste_valve, times=2, volume="large")

    # 8) 读数与换算：先读取消解器结果，再统一交给算法函数处理。
    absorbance = read_digest_value(ctx)
    concentration = compute_concentration(absorbance, standard_concentration)

    # 9) 收尾：排空当前反应液，做一次系统清洗，最后统一关阀。
    empty_digestor(ctx, recipe.waste_valve)
    clean_system(ctx)
    close_all_valves(ctx)

    return {
        "absorbance": absorbance,
        "concentration": concentration,
    }


def main() -> None:
    """脚本入口。

    统一负责三件事：
    - 组装本次运行需要的硬件上下文
    - 执行一轮完整分析流程
    - 无论中间是否报错，最后都做安全关闭
    """

    ctx = None
    try:
        ctx = build_hardware(DEFAULT_CONFIG)
        result = run_water_analysis(
            ctx,
            standard_concentration=DEFAULT_CONFIG.recipe.standard_concentration,
        )
        print(f"[RESULT] absorbance={result['absorbance']:.2f}")
        print(f"[RESULT] concentration={result['concentration']:.2f}")
    finally:
        safe_shutdown(ctx)


if __name__ == "__main__":
    main()
