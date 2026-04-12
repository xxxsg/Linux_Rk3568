from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from config import AppConfig, DEFAULT_CONFIG
from hardware import HardwareContext


# ==================== 异常与数据结构层 ====================
# 这一层只定义元语层内部共用的异常类型和数据载体。
# 不负责硬件操作，也不负责流程编排，作用是给后续动作提供统一表达。
# 包含：
# - RecipeError：流程执行中的业务异常。
# - DigestSignal：一次光学读数得到的 6 个关键电压数据。
class RecipeError(RuntimeError):
    """流程执行期间的业务异常。"""

    pass


@dataclass(frozen=True)
class DigestSignal:
    """一次完整读数过程中采集到的 6 个关键电压。"""

    vbias_m: float
    vbias_r: float
    vm_0: float
    vr_0: float
    vm_s: float
    vr_s: float


# ==================== 通用时序与判定层 ====================
# 这一层提供最基础的“时间”和“条件”能力，例如延时、轮询、稳定判定。
# 它不关心具体是在判液位、温度还是别的状态，只负责抽象出可复用的等待机制。
# 包含：
# - sleep_ms()：毫秒级延时。
# - wait_until()：在超时前循环检查条件是否成立。
# - stable_truth()：要求条件连续多次成立，过滤瞬时抖动。
def sleep_ms(ms: int | float) -> None:
    """毫秒级等待封装。"""

    time.sleep(float(ms) / 1000.0)


def wait_until(cond_fn: Callable[[], bool], timeout_ms: int, poll_ms: int = 50) -> bool:
    """在超时前持续轮询某个条件是否成立。"""

    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if cond_fn():
            return True
        sleep_ms(poll_ms)
    return cond_fn()


def stable_truth(cond_fn: Callable[[], bool], config: AppConfig = DEFAULT_CONFIG) -> bool:
    """要求条件连续多次成立，降低传感器抖动带来的误判。"""

    for _ in range(config.timing.stable_sample_count):
        if not cond_fn():
            return False
        sleep_ms(config.timing.stable_sample_period_ms)
    return True


# ==================== 液路状态判定层 ====================
# 这一层把底层传感器读数转换成流程可用的状态语义。
# 例如“计量单元已满”“计量单元已空”，上层动作只依赖这些判断，不直接碰阈值细节。
# 包含：
# - close_all_valves()：统一关闭全部液路阀门。
# - is_meter_full()：判断计量单元是否达到大/小体积目标液位。
# - is_meter_empty()：判断计量单元是否已经排空。
def close_all_valves(ctx: HardwareContext) -> None:
    """统一关闭所有液路阀门。"""

    ctx.valve.close_all()


def is_meter_full(ctx: HardwareContext, volume: str, baseline_mv: float | None = None) -> bool:
    """判断计量单元是否达到目标液位。
    
    baseline_mv 为吸液前读取的固定基准电压，若不传则实时读取。
    当电压上升百分比超过阈值时判定到位。
    """
    thresholds = DEFAULT_CONFIG.thresholds
    change_pct = thresholds.voltage_change_percent / 100.0  # 转换为小数
    
    if volume == "large":
        baseline = baseline_mv if baseline_mv is not None else ctx.meter_optics.read_upper_mv()
        if baseline == 0:
            return False  # 避免除零
        target_mv = baseline * (1 + change_pct)  # 电压上升到该值视为到位
        return stable_truth(lambda: ctx.meter_optics.read_upper_mv() >= target_mv)
    
    if volume == "small":
        baseline = baseline_mv if baseline_mv is not None else ctx.meter_optics.read_lower_mv()
        if baseline == 0:
            return False  # 避免除零
        target_mv = baseline * (1 + change_pct)  # 电压上升到该值视为到位
        return stable_truth(lambda: ctx.meter_optics.read_lower_mv() >= target_mv)
    
    raise ValueError(f"unsupported volume: {volume}")


def is_meter_empty(ctx: HardwareContext, baseline_mv: float | None = None) -> bool:
    """判断计量单元是否已经排空。
    
    baseline_mv 为排液前读取的固定基准电压（有液状态），若不传则实时读取。
    当电压下降百分比超过阈值时判定排空。
    """
    thresholds = DEFAULT_CONFIG.thresholds
    change_pct = thresholds.voltage_change_percent / 100.0  # 转换为小数
    
    baseline = baseline_mv if baseline_mv is not None else ctx.meter_optics.read_upper_mv()
    if baseline == 0:
        return False  # 避免除零
    target_mv = baseline * (1 - change_pct)  # 电压下降到该值视为排空
    return stable_truth(lambda: ctx.meter_optics.read_upper_mv() <= target_mv)


# ==================== 液路路由元语层 ====================
# 这一层只负责把液路切到指定方向，也就是决定哪些阀门该开、哪些该关。
# 它只做通路建立，不做吸液、排液，不等待液位结果，是更纯粹的“路由原语”。
# 包含：
# - route_source_to_meter()：建立“液源 -> 计量单元”通路。
# - route_meter_to_targets()：建立“计量单元 -> 目标端”通路。
# - route_digestor_to_meter()：建立“消解器 -> 计量单元”通路。
def route_source_to_meter(ctx: HardwareContext, source_name: str) -> None:
    """切换液路到"液源 -> 计量单元"方向。"""

    close_all_valves(ctx)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)
    ctx.valve.open([source_name])
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def route_meter_to_targets(ctx: HardwareContext, targets: list[str]) -> None:
    """切换液路到"计量单元 -> 目标端"方向。"""

    close_all_valves(ctx)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)
    ctx.valve.open(targets)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def route_digestor_to_meter(ctx: HardwareContext) -> None:
    """切换液路到"消解器 -> 计量单元"方向。"""

    close_all_valves(ctx)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)
    ctx.valve.open(list(DEFAULT_CONFIG.recipe.digestor_valves))
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


# ==================== 执行动作元语层 ====================
# 这一层开始把“路由 + 泵动作 + 状态判定”组合起来，形成真正能被流程复用的动作原语。
# 比如吸液、排液、加样、冲洗都在这里实现，但仍然不承载完整实验流程编排。
# 包含：
# - start_pump_in_background()：在后台线程启动连续泵动作。
# - aspirate()：从指定液源吸液到计量单元。
# - dispense()：把计量单元中的液体排到目标端。
# - add_to_digestor()：把指定液体经计量单元加入消解器。
# - rinse_to_waste()：用小体积液体润洗支路后排到废液。
# - flush_pipeline()：重复执行吸液与排废，用于主通路冲洗。
def start_pump_in_background(pump_action: Callable[[], None]) -> threading.Thread:
    """将连续泵动作放到后台线程中执行。"""

    worker = threading.Thread(target=pump_action, daemon=True)
    worker.start()
    return worker


def aspirate(ctx: HardwareContext, source_name: str, volume: str) -> None:
    """从指定液源吸液到计量单元。

    流程：
    1. 切换到"液源 -> 计量单元"
    2. 开灯并等待光路稳定
    3. 读取当前空管基准电压
    4. 后台启动连续吸液
    5. 轮询液位是否到达目标位置
    6. 无论成功或失败，都停泵并关闭阀门
    """

    timeout_ms = (
        DEFAULT_CONFIG.timing.take_large_timeout_ms
        if volume == "large"
        else DEFAULT_CONFIG.timing.take_small_timeout_ms
    )

    route_source_to_meter(ctx, source_name)
    ctx.meter_optics.light_on()
    sleep_ms(DEFAULT_CONFIG.timing.optics_warmup_ms)
    if volume == "large":
        baseline = ctx.meter_optics.read_upper_mv()
    else:
        baseline = ctx.meter_optics.read_lower_mv()
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    try:
        ok = wait_until(lambda: is_meter_full(ctx, volume, baseline), timeout_ms, poll_ms=50)
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_valves(ctx)

    if not ok:
        raise RecipeError(f"aspirate timeout: source={source_name}, volume={volume}")


def dispense(ctx: HardwareContext, targets: list[str]) -> None:
    """将计量单元中的液体排到目标端。"""

    route_meter_to_targets(ctx, targets)
    # 排液前读取固定基准电压（有液状态），避免轮询过程中基准漂移
    baseline = ctx.meter_optics.read_upper_mv()
    worker = start_pump_in_background(ctx.pump.dispense_continuous)
    try:
        ok = wait_until(
            lambda: is_meter_empty(ctx, baseline),
            DEFAULT_CONFIG.timing.dispense_timeout_ms,
            poll_ms=50,
        )
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)

    if not ok:
        close_all_valves(ctx)
        raise RecipeError(f"dispense timeout: targets={targets}")

    ctx.pump.dispense_time(DEFAULT_CONFIG.timing.supplement_blow_ms / 1000.0)
    close_all_valves(ctx)


def add_to_digestor(ctx: HardwareContext, source_name: str, volume: str) -> None:
    """将指定液体通过计量单元送入消解器。"""

    aspirate(ctx, source_name, volume)
    dispense(ctx, list(DEFAULT_CONFIG.recipe.digestor_valves))


def rinse_to_waste(ctx: HardwareContext, source_name: str, waste_name: str) -> None:
    """用小体积液体润洗当前支路后排到废液。"""

    aspirate(ctx, source_name, "small")
    dispense(ctx, [waste_name])


def flush_pipeline(
    ctx: HardwareContext,
    source_name: str,
    waste_name: str,
    times: int,
    volume: str,
) -> None:
    """重复执行吸液与排废，完成主通路冲洗。"""

    for _ in range(times):
        aspirate(ctx, source_name, volume)
        dispense(ctx, [waste_name])
        sleep_ms(200)


# ==================== 消解器操作元语层 ====================
# 这一层聚焦消解器这个特定反应单元的液体操作。
# 它在通用吸排动作之上，补充“回抽、排空、通气搅拌”这些只对消解器有意义的原语。
# 包含：
# - pull_digestor_to_meter()：把消解器中的液体回抽到计量单元。
# - empty_digestor()：将消解器内容物排到指定废液端。
# - aerate_digestor()：向消解器通气，用于搅拌或曝气。
def pull_digestor_to_meter(ctx: HardwareContext) -> None:
    """将消解器中的液体回抽到计量单元。"""

    route_digestor_to_meter(ctx)
    # 回抽前读取固定基准电压（空管状态）
    baseline = ctx.meter_optics.read_upper_mv()
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    try:
        ok = wait_until(
            lambda: is_meter_full(ctx, "large", baseline),
            DEFAULT_CONFIG.timing.pull_digestor_timeout_ms,
            poll_ms=50,
        )
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_valves(ctx)

    if not ok:
        raise RecipeError("pull digestor timeout")


def empty_digestor(ctx: HardwareContext, waste_name: str) -> None:
    """排空消解器内容物。"""

    pull_digestor_to_meter(ctx)
    dispense(ctx, [waste_name])


def aerate_digestor(ctx: HardwareContext, duration_ms: int) -> None:
    """向消解器通气搅拌一段时间。"""

    close_all_valves(ctx)
    ctx.valve.open(list(DEFAULT_CONFIG.recipe.digestor_valves))
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)
    try:
        ctx.pump.dispense_time(duration_ms / 1000.0)
    finally:
        close_all_valves(ctx)


# ==================== 温控元语层 ====================
# 这一层负责温度闭环相关动作，把温度采样与加热开关封装成独立原语。
# 上层流程只需要给出目标温度和时长，不需要关心回差控制和轮询细节。
# 包含：
# - _set_heater_for_target()：按回差规则决定加热开或关。
# - heat_and_hold()：升温到目标值后继续保温指定时长。
def _set_heater_for_target(
    ctx: HardwareContext,
    current_temp_c: float,
    target_temp_c: float,
    hysteresis_c: float,
) -> None:
    """按回差策略控制加热开关。"""

    if current_temp_c < target_temp_c - hysteresis_c:
        ctx.heater.on()
    elif current_temp_c >= target_temp_c:
        ctx.heater.off()


def heat_and_hold(ctx: HardwareContext, target_temp_c: float, hold_ms: int) -> None:
    """加热到目标温度后再保温指定时长。"""

    timing = DEFAULT_CONFIG.timing
    hysteresis_c = DEFAULT_CONFIG.temperature.heater_hysteresis_c
    poll_ms = timing.heat_poll_ms
    heat_deadline = time.monotonic() + timing.heat_up_timeout_ms / 1000.0

    try:
        while True:
            current_temp_c = ctx.temp_sensor.read_temperature_c()
            _set_heater_for_target(ctx, current_temp_c, target_temp_c, hysteresis_c)
            if current_temp_c >= target_temp_c:
                break
            if time.monotonic() >= heat_deadline:
                raise RecipeError(f"heat timeout: target_temp_c={target_temp_c}")
            sleep_ms(poll_ms)

        hold_deadline = time.monotonic() + hold_ms / 1000.0
        while time.monotonic() < hold_deadline:
            current_temp_c = ctx.temp_sensor.read_temperature_c()
            _set_heater_for_target(ctx, current_temp_c, target_temp_c, hysteresis_c)
            sleep_ms(poll_ms)
    finally:
        ctx.heater.off()


# ==================== 光学读数元语层 ====================
# 这一层负责消解读数时的光路切换和采样顺序控制。
# 它输出的是浓度计算所需的原始电压，不直接承担吸光度或浓度公式计算。
# 包含：
# - read_digest_signal()：按固定顺序采集 Vbias、空白和样品三组电压。
def read_digest_signal(ctx: HardwareContext) -> DigestSignal:
    """按约定流程读取浓度计算所需的 6 个电压。"""

    optics = ctx.digest_optics

    # 1. 断开放大通道，测量两路 Vbias。
    optics.light_off()
    optics.disconnect_paths()
    sleep_ms(DEFAULT_CONFIG.timing.optics_warmup_ms)
    vbias_m = optics.read_measure_mv()
    vbias_r = optics.read_reference_mv()

    # 2. 闭合通道并关闭光源，读取暗电流/空白电压。
    optics.connect_paths()
    optics.light_off()
    sleep_ms(DEFAULT_CONFIG.timing.optics_warmup_ms)
    vm_0 = optics.read_measure_mv()
    vr_0 = optics.read_reference_mv()

    # 3. 闭合通道并打开光源，读取样品电压。
    optics.connect_paths()
    optics.light_on()
    sleep_ms(DEFAULT_CONFIG.timing.optics_warmup_ms)
    vm_s = optics.read_measure_mv()
    vr_s = optics.read_reference_mv()
    optics.light_off()

    return DigestSignal(
        vbias_m=vbias_m,
        vbias_r=vbias_r,
        vm_0=vm_0,
        vr_0=vr_0,
        vm_s=vm_s,
        vr_s=vr_s,
    )
