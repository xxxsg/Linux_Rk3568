"""合并后的流程文件（基础动作 + 工序动作）。"""

import time
from config import *


def wait_until(cond_fn, timeout_ms, poll_ms=50):
    """轮询等待条件成立。"""
    start = time.time()
    while (not cond_fn()) and ((time.time() - start) * 1000 < timeout_ms):
        time.sleep(poll_ms / 1000.0)
    return cond_fn()


def is_full(meter_optics, volume):
    """满位判定（已移除去抖，直接单次阈值判断）。"""
    if volume == "大":
        return meter_optics.read_upper_transmittance() <= UPPER_FULL_THRESHOLD_MV
    return meter_optics.read_lower_transmittance() <= LOWER_FULL_THRESHOLD_MV


def is_empty(meter_optics):
    """空位判定（已移除去抖）。"""
    return meter_optics.read_upper_transmittance() >= EMPTY_THRESHOLD_MV


def route_source_to_meter(valve, source_name):
    """路由：源液 -> 计量单元入口。"""
    valve.close_all()
    valve.open([source_name, "计量单元入口"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)  # 阀切换稳定时间


def route_meter_to_target(valve, target_valves):
    """路由：计量单元 -> 目标阀。"""
    valve.close_all()
    valve.open(target_valves)
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)


def take(ctx, source_name, volume):
    """取液动作。"""
    timeout = TIMEOUT_TAKE_LARGE_MS if volume == "大" else TIMEOUT_TAKE_SMALL_MS
    route_source_to_meter(ctx.valve, source_name)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ok = wait_until(lambda: is_full(ctx.meter_optics, volume), timeout, 50)
    ctx.pump.disable()
    ctx.valve.close_all()
    return ok


def dispense(ctx, target_valves):
    """打液动作。"""
    route_meter_to_target(ctx.valve, target_valves)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    ok = wait_until(lambda: is_empty(ctx.meter_optics), TIMEOUT_DISPENSE_MS, 50)
    ctx.pump.disable()

    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    time.sleep(SUPPLEMENT_BLOW_MS / 1000.0)
    ctx.pump.disable()

    ctx.valve.close_all()
    return ok


def aerate_stir_digestor(ctx, duration_ms):
    """通气搅拌。"""
    ctx.valve.close_all()
    ctx.valve.open(["消解器上阀", "消解器下阀"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    time.sleep(duration_ms / 1000.0)
    ctx.pump.disable()
    ctx.valve.close_all()


def pull_digestor_to_meter(ctx):
    """抽取消解器液体到计量单元。"""
    ctx.valve.close_all()
    ctx.valve.open(["消解器下阀", "消解器上阀", "计量单元入口"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ok = wait_until(lambda: is_full(ctx.meter_optics, "大"), TIMEOUT_PULL_DIGESTOR_MS, 50)
    ctx.pump.disable()
    ctx.valve.close_all()
    return ok


# --------------------- 工序封装 ---------------------

def add_to_digestor(ctx, source_name, volume):
    return take(ctx, source_name, volume) and dispense(ctx, ["消解器下阀", "消解器上阀"])


def rinse(ctx, source_name, waste_valve):
    return take(ctx, source_name, "小") and dispense(ctx, [waste_valve])


def flush_pipeline(ctx, source_name, waste_valve, times, volume):
    ok = True
    for _ in range(times):
        ok = take(ctx, source_name, volume) and ok
        ok = dispense(ctx, [waste_valve]) and ok
        time.sleep(0.2)
    return ok


def empty_digestor(ctx, waste_valve):
    return pull_digestor_to_meter(ctx) and dispense(ctx, [waste_valve])


def full_clean(ctx):
    ok1 = add_to_digestor(ctx, "标一", "大")
    time.sleep(20)
    ok2 = empty_digestor(ctx, "废液1")
    ok3 = flush_pipeline(ctx, "标一", "废液1", 3, "大")
    return ok1 and ok2 and ok3


def heat_and_hold(temp_ctrl, target_temp, hold_ms):
    temp_ctrl.start(target_temp)
    elapsed_ms = 0
    while temp_ctrl.read_temperature() < target_temp:
        time.sleep(0.5)
        elapsed_ms += 500
        if elapsed_ms >= HEAT_UP_TIMEOUT_MS:
            break
    temp_ctrl.hold(hold_ms)
    temp_ctrl.stop()


def read_digest_value(digest_optics, preheat_ms):
    time.sleep(preheat_ms / 1000.0)
    return digest_optics.read_absorbance()


def stir_once(ctx, duration_ms):
    aerate_stir_digestor(ctx, duration_ms)
