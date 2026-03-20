from __future__ import annotations

import threading
import time
from typing import Any

from config import AppConfig, DEFAULT_CONFIG


class RecipeError(RuntimeError):
    """流程执行中的业务异常。"""

    pass


def sleep_ms(ms: int | float) -> None:
    """毫秒级休眠辅助函数。"""

    time.sleep(float(ms) / 1000.0)


def wait_until(cond_fn, timeout_ms: int, poll_ms: int = 50) -> bool:
    """轮询等待条件成立，超时后返回最终判断结果。"""

    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if cond_fn():
            return True
        sleep_ms(poll_ms)
    return cond_fn()


def stable_truth(cond_fn, config: AppConfig = DEFAULT_CONFIG) -> bool:
    """连续多次满足条件才认为成立，用于消抖。"""

    for _ in range(config.timing.stable_sample_count):
        if not cond_fn():
            return False
        sleep_ms(config.timing.stable_sample_period_ms)
    return True


def is_meter_full(hw: dict[str, Any], volume: str) -> bool:
    """根据上下光学通道判断计量单元是否到达满位。"""

    thresholds = DEFAULT_CONFIG.thresholds
    if volume == "large":
        channel = DEFAULT_CONFIG.ads.meter_upper_channel
        return stable_truth(lambda: float(hw["ads1115"].read_voltage(channel)) <= thresholds.upper_full_mv, DEFAULT_CONFIG)
    if volume == "small":
        channel = DEFAULT_CONFIG.ads.meter_lower_channel
        return stable_truth(lambda: float(hw["ads1115"].read_voltage(channel)) <= thresholds.lower_full_mv, DEFAULT_CONFIG)
    raise ValueError(f"unsupported volume: {volume}")


def is_meter_empty(hw: dict[str, Any]) -> bool:
    """根据上光学通道判断计量单元是否排空。"""

    channel = DEFAULT_CONFIG.ads.meter_upper_channel
    return stable_truth(
        lambda: float(hw["ads1115"].read_voltage(channel)) >= DEFAULT_CONFIG.thresholds.empty_mv,
        DEFAULT_CONFIG,
    )


def route_source_to_meter(hw: dict[str, Any], source_name: str) -> None:
    """建立“源液 -> 计量单元”的液路。"""

    for pin in hw["valves"].values():
        pin.write(False)
    # 计量单元本身为常开，源液进入计量单元时只需打开源液阀。
    hw["valves"][source_name].write(True)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def route_meter_to_target(hw: dict[str, Any], targets: list[str]) -> None:
    """建立“计量单元 -> 目标位置”的液路。"""

    for pin in hw["valves"].values():
        pin.write(False)
    for name in targets:
        hw["valves"][name].write(True)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)


def start_pump_in_background(pump_action):
    """Pump 的连续动作是阻塞的，这里放到后台线程执行。"""

    worker = threading.Thread(target=pump_action, daemon=True)
    worker.start()
    return worker


def aspirate(hw: dict[str, Any], source_name: str, volume: str) -> None:
    """吸液到计量单元，直到满位或超时。"""

    timeout_ms = (
        DEFAULT_CONFIG.timing.take_large_timeout_ms
        if volume == "large"
        else DEFAULT_CONFIG.timing.take_small_timeout_ms
    )

    route_source_to_meter(hw, source_name)
    worker = start_pump_in_background(hw["pump"].aspirate_continuous)
    try:
        ok = wait_until(lambda: is_meter_full(hw, volume), timeout_ms, poll_ms=50)
    finally:
        hw["pump"].stop()
        worker.join(timeout=2.0)
        for pin in hw["valves"].values():
            pin.write(False)

    if not ok:
        raise RecipeError(f"aspirate timeout: source={source_name}, volume={volume}")


def dispense(hw: dict[str, Any], targets: list[str]) -> None:
    """将计量单元中的液体打到目标阀路。"""

    route_meter_to_target(hw, targets)
    worker = start_pump_in_background(hw["pump"].dispense_continuous)
    try:
        ok = wait_until(lambda: is_meter_empty(hw), DEFAULT_CONFIG.timing.dispense_timeout_ms, poll_ms=50)
    finally:
        hw["pump"].stop()
        worker.join(timeout=2.0)

    if not ok:
        for pin in hw["valves"].values():
            pin.write(False)
        raise RecipeError(f"dispense timeout: targets={targets}")

    # 主排液完成后补吹一下，尽量减少残液。
    hw["pump"].dispense_time(DEFAULT_CONFIG.timing.supplement_blow_ms / 1000.0)
    for pin in hw["valves"].values():
        pin.write(False)


def add_to_digestor(hw: dict[str, Any], source_name: str, volume: str) -> None:
    """从源液吸液后打入消解器。"""

    aspirate(hw, source_name, volume)
    dispense(hw, list(DEFAULT_CONFIG.recipe.digestor_valves))


def rinse_to_waste(hw: dict[str, Any], source_name: str, waste_name: str) -> None:
    """小体积润洗后直接排入废液。"""

    aspirate(hw, source_name, "small")
    dispense(hw, [waste_name])


def flush_pipeline(hw: dict[str, Any], source_name: str, waste_name: str, times: int, volume: str) -> None:
    """重复执行吸液+排废液，用于管路冲洗。"""

    for _ in range(times):
        aspirate(hw, source_name, volume)
        dispense(hw, [waste_name])
        sleep_ms(200)


def pull_digestor_to_meter(hw: dict[str, Any]) -> None:
    """将消解器内液体抽回计量单元，便于后续排空。"""

    for pin in hw["valves"].values():
        pin.write(False)
    for name in DEFAULT_CONFIG.recipe.digestor_valves:
        hw["valves"][name].write(True)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)

    worker = start_pump_in_background(hw["pump"].aspirate_continuous)
    try:
        ok = wait_until(
            lambda: is_meter_full(hw, "large"),
            DEFAULT_CONFIG.timing.pull_digestor_timeout_ms,
            poll_ms=50,
        )
    finally:
        hw["pump"].stop()
        worker.join(timeout=2.0)
        for pin in hw["valves"].values():
            pin.write(False)

    if not ok:
        raise RecipeError("pull digestor timeout")


def empty_digestor(hw: dict[str, Any], waste_name: str) -> None:
    """排空消解器内容物到指定废液口。"""

    pull_digestor_to_meter(hw)
    dispense(hw, [waste_name])


def aerate_digestor(hw: dict[str, Any], duration_ms: int) -> None:
    """通过泵打气，对消解器进行通气搅拌。"""

    for pin in hw["valves"].values():
        pin.write(False)
    for name in DEFAULT_CONFIG.recipe.digestor_valves:
        hw["valves"][name].write(True)
    sleep_ms(DEFAULT_CONFIG.timing.valve_settle_ms)
    try:
        hw["pump"].dispense_time(duration_ms / 1000.0)
    finally:
        for pin in hw["valves"].values():
            pin.write(False)


def heat_and_hold(hw: dict[str, Any], target_temp_c: float, hold_ms: int) -> None:
    """等待温度达到目标值，并保持一段时间。"""

    ok = wait_until(
        lambda: float(hw["max31865"].read_temperature()) >= target_temp_c,
        DEFAULT_CONFIG.timing.heat_up_timeout_ms,
        poll_ms=500,
    )
    if not ok:
        raise RecipeError(f"heat timeout: target_temp_c={target_temp_c}")
    sleep_ms(hold_ms)


def read_digest_value(hw: dict[str, Any]) -> float:
    """读消解吸光度前先等待光学通道稳定。"""

    sleep_ms(DEFAULT_CONFIG.timing.optics_warmup_ms)
    channel = DEFAULT_CONFIG.ads.digest_channel
    return float(hw["ads1115"].read_voltage(channel))


def compute_concentration(absorbance: float, standard_concentration: float) -> float:
    """浓度换算占位实现，后续可替换成标定公式。"""

    return absorbance * standard_concentration
