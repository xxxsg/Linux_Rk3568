from __future__ import annotations

import threading
import time
from collections.abc import Callable

from config import AppConfig, DEFAULT_CONFIG
from hardware import HardwareContext


class RecipeError(RuntimeError):
    """流程执行中的业务异常。

    这类异常表示“工艺动作没有按预期完成”，
    比如吸液超时、排液超时、升温超时。
    """


def sleep_ms(ms: int | float) -> None:
    """毫秒级睡眠封装。

    主流程和原语层统一用这个函数表示“等待硬件稳定”或“等待反应时间”，
    这样比到处直接写 `time.sleep()` 更容易看出意图。
    """

    time.sleep(float(ms) / 1000.0)


def wait_until(cond_fn: Callable[[], bool], timeout_ms: int, poll_ms: int = 50) -> bool:
    """在超时时间内反复轮询一个条件。

    常用于等待：
    - 计量单元达到满液位
    - 计量单元回到空液位
    - 温度达到目标值
    """

    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if cond_fn():
            return True
        sleep_ms(poll_ms)
    return cond_fn()


def stable_truth(cond_fn: Callable[[], bool], config: AppConfig = DEFAULT_CONFIG) -> bool:
    """要求条件连续多次成立，避免因为传感器抖动误判。

    单次读到“满”或“空”并不一定可靠，
    所以这里用连续采样做一个很轻的去抖。
    """

    for _ in range(config.timing.stable_sample_count):
        if not cond_fn():
            return False
        sleep_ms(config.timing.stable_sample_period_ms)
    return True


def close_all_valves(ctx: HardwareContext) -> None:
    """统一关闭液路阀。

    这是最基础的安全动作：
    - 切换液路前先全关，避免两条支路误通
    - 工艺动作结束后再全关，保证系统收尾一致
    """

    ctx.valve.close_all()


def is_meter_full(ctx: HardwareContext, volume: str) -> bool:
    """判断计量单元是否已经达到目标液位。

    `large` 和 `small` 分别对应不同液位阈值：
    - 大体积看上液位
    - 小体积看下液位
    """

    thresholds = DEFAULT_CONFIG.thresholds
    if volume == "large":
        return stable_truth(lambda: ctx.meter_optics.read_upper_mv() <= thresholds.upper_full_mv)
    if volume == "small":
        return stable_truth(lambda: ctx.meter_optics.read_lower_mv() <= thresholds.lower_full_mv)
    raise ValueError(f"unsupported volume: {volume}")


def is_meter_empty(ctx: HardwareContext) -> bool:
    """判断计量单元是否已经排空。"""

    return stable_truth(
        lambda: ctx.meter_optics.read_upper_mv() >= DEFAULT_CONFIG.thresholds.empty_mv,
    )


def route_source_to_meter(ctx: HardwareContext, source_name: str) -> None:
    """切换液路到“液源 -> 计量单元”。

    这里不直接启动泵，只负责把液路切对。
    真正的吸液动作由 `aspirate()` 完成。
    """

    close_all_valves(ctx)
    ctx.valve.open([source_name])
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def route_meter_to_targets(ctx: HardwareContext, targets: list[str]) -> None:
    """切换液路到“计量单元 -> 目标端”。

    `targets` 允许是多个阀门，
    例如把计量单元连到消解器相关的几条通路。
    """

    close_all_valves(ctx)
    ctx.valve.open(targets)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def route_digestor_to_meter(ctx: HardwareContext) -> None:
    """切换液路到“消解器 -> 计量单元”。

    这个动作主要给“抽空消解器”使用，
    先把消解器中的液体回抽到计量单元，再统一排到废液。
    """

    close_all_valves(ctx)
    ctx.valve.open(list(DEFAULT_CONFIG.recipe.digestor_valves))
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def start_pump_in_background(pump_action: Callable[[], None]) -> threading.Thread:
    """把连续泵动作放到后台线程执行。

    因为 `aspirate_continuous()` 和 `dispense_continuous()` 是阻塞式动作，
    主线程需要一边让泵运行，一边轮询液位是否到位。
    """

    worker = threading.Thread(target=pump_action, daemon=True)
    worker.start()
    return worker


def aspirate(ctx: HardwareContext, source_name: str, volume: str) -> None:
    """从指定液源吸液到计量单元。

    流程顺序是：
    1. 先把液路切成“液源 -> 计量单元”
    2. 启动连续吸液
    3. 轮询液位是否到达目标位置
    4. 无论成功还是失败，都停泵并关阀
    """

    timeout_ms = (
        DEFAULT_CONFIG.timing.take_large_timeout_ms
        if volume == "large"
        else DEFAULT_CONFIG.timing.take_small_timeout_ms
    )

    route_source_to_meter(ctx, source_name)
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    try:
        ok = wait_until(lambda: is_meter_full(ctx, volume), timeout_ms, poll_ms=50)
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_valves(ctx)

    if not ok:
        raise RecipeError(f"aspirate timeout: source={source_name}, volume={volume}")


def dispense(ctx: HardwareContext, targets: list[str]) -> None:
    """把计量单元中的液体排到目标端。

    流程顺序和吸液类似：
    1. 先把液路切成“计量单元 -> 目标端”
    2. 启动连续排液
    3. 轮询计量单元是否排空
    4. 最后补吹一小段时间，把余液尽量赶净
    """

    route_meter_to_targets(ctx, targets)
    worker = start_pump_in_background(ctx.pump.dispense_continuous)
    try:
        ok = wait_until(
            lambda: is_meter_empty(ctx),
            DEFAULT_CONFIG.timing.dispense_timeout_ms,
            poll_ms=50,
        )
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)

    if not ok:
        close_all_valves(ctx)
        raise RecipeError(f"dispense timeout: targets={targets}")

    # 补吹一小段时间，尽量把计量单元和末端支路里的余液排净。
    ctx.pump.dispense_time(DEFAULT_CONFIG.timing.supplement_blow_ms / 1000.0)
    close_all_valves(ctx)


def add_to_digestor(ctx: HardwareContext, source_name: str, volume: str) -> None:
    """把某一路液体送入消解器。

    这是一个组合原语：
    - 先从液源吸到计量单元
    - 再从计量单元排到消解器
    """

    aspirate(ctx, source_name, volume)
    dispense(ctx, list(DEFAULT_CONFIG.recipe.digestor_valves))


def rinse_to_waste(ctx: HardwareContext, source_name: str, waste_name: str) -> None:
    """用小体积液体润洗当前支路，并排到废液。

    目的不是正式加样，而是先让本支路里的残液被新液体顶掉一部分，
    降低交叉污染风险。
    """

    aspirate(ctx, source_name, "small")
    dispense(ctx, [waste_name])


def flush_pipeline(
    ctx: HardwareContext,
    source_name: str,
    waste_name: str,
    times: int,
    volume: str,
) -> None:
    """重复执行吸液和排废，完成主管路冲洗。

    这通常用在某个试剂步骤后，
    目的是把主管路尽量恢复到更干净的状态。
    """

    for _ in range(times):
        aspirate(ctx, source_name, volume)
        dispense(ctx, [waste_name])
        sleep_ms(200)


def pull_digestor_to_meter(ctx: HardwareContext) -> None:
    """把消解器中的液体回抽到计量单元。

    这是“排空消解器”前的上半步，
    因为当前系统是通过计量单元作为中间站来做统一排废的。
    """

    route_digestor_to_meter(ctx)
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    try:
        ok = wait_until(
            lambda: is_meter_full(ctx, "large"),
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
    """排空消解器。

    做法不是直接从消解器打到废液，
    而是先回抽到计量单元，再统一排到废液阀。
    """

    pull_digestor_to_meter(ctx)
    dispense(ctx, [waste_name])


def aerate_digestor(ctx: HardwareContext, duration_ms: int) -> None:
    """向消解器通气搅拌。

    这里复用泵的排液方向，把空气或气泡推入消解器通路，
    以达到中途混匀反应体系的目的。
    """

    close_all_valves(ctx)
    ctx.valve.open(list(DEFAULT_CONFIG.recipe.digestor_valves))
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)
    try:
        ctx.pump.dispense_time(duration_ms / 1000.0)
    finally:
        close_all_valves(ctx)


def heat_and_hold(ctx: HardwareContext, target_temp_c: float, hold_ms: int) -> None:
    """等待消解器升温到目标值，并继续保温一段时间。"""

    ok = wait_until(
        lambda: ctx.temp_sensor.read_temperature_c() >= target_temp_c,
        DEFAULT_CONFIG.timing.heat_up_timeout_ms,
        poll_ms=500,
    )
    if not ok:
        raise RecipeError(f"heat timeout: target_temp_c={target_temp_c}")
    sleep_ms(hold_ms)


def read_digest_value(ctx: HardwareContext) -> float:
    """读取消解器最终结果。

    读之前先留一小段预热/稳定时间，
    再从消解读数通道取值。
    """

    sleep_ms(DEFAULT_CONFIG.timing.optics_warmup_ms)
    return ctx.digest_optics.read_absorbance_mv()
