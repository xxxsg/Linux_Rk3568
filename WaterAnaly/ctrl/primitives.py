"""Primitive actions: route, take, dispense, and core state checks."""

import time

from config import (
    DIR_FORWARD,
    DIR_REVERSE,
    SAMPLE_PERIOD_MS,
    STABLE_COUNT,
    VALVE_SWITCH_STABLE_MS,
    TIMEOUT_TAKE_LARGE_MS,
    TIMEOUT_TAKE_SMALL_MS,
    TIMEOUT_DISPENSE_MS,
    TIMEOUT_PULL_DIGESTOR_MS,
    SUPPLEMENT_BLOW_MS,
    UPPER_FULL_THRESHOLD_MV,
    LOWER_FULL_THRESHOLD_MV,
    EMPTY_THRESHOLD_MV,
)


def sleep_ms(ms):
    time.sleep(ms / 1000.0)


def now_ms():
    return int(time.time() * 1000)


def wait_until(cond_fn, timeout_ms, poll_ms=50):
    start = now_ms()
    while (not cond_fn()) and (now_ms() - start < timeout_ms):
        sleep_ms(poll_ms)
    return cond_fn()


def stable_true(cond_fn):
    ok = 0
    for _ in range(STABLE_COUNT):
        if cond_fn():
            ok += 1
        sleep_ms(SAMPLE_PERIOD_MS)
    return ok == STABLE_COUNT


def is_full(meter_optics, volume):
    if volume == "大":
        return stable_true(
            lambda: meter_optics.read_upper_transmittance() <= UPPER_FULL_THRESHOLD_MV
        )
    return stable_true(
        lambda: meter_optics.read_lower_transmittance() <= LOWER_FULL_THRESHOLD_MV
    )


def is_empty(meter_optics):
    return stable_true(
        lambda: meter_optics.read_upper_transmittance() >= EMPTY_THRESHOLD_MV
    )


def route_source_to_meter(valve, source_name):
    valve.close_all()
    valve.open([source_name, "计量单元入口"])
    sleep_ms(VALVE_SWITCH_STABLE_MS)


def route_meter_to_target(valve, target_valves):
    valve.close_all()
    valve.open(target_valves)
    sleep_ms(VALVE_SWITCH_STABLE_MS)


def take(ctx, source_name, volume):
    timeout = TIMEOUT_TAKE_LARGE_MS if volume == "大" else TIMEOUT_TAKE_SMALL_MS
    route_source_to_meter(ctx.valve, source_name)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ok = wait_until(lambda: is_full(ctx.meter_optics, volume), timeout, 50)
    ctx.pump.disable()
    ctx.valve.close_all()
    return ok


def dispense(ctx, target_valves):
    route_meter_to_target(ctx.valve, target_valves)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    ok = wait_until(lambda: is_empty(ctx.meter_optics), TIMEOUT_DISPENSE_MS, 50)
    ctx.pump.disable()

    # blow compensation
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    sleep_ms(SUPPLEMENT_BLOW_MS)
    ctx.pump.disable()

    ctx.valve.close_all()
    return ok


def aerate_stir_digestor(ctx, duration_ms):
    ctx.valve.close_all()
    ctx.valve.open(["消解器上阀", "消解器下阀"])
    sleep_ms(VALVE_SWITCH_STABLE_MS)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    sleep_ms(duration_ms)
    ctx.pump.disable()
    ctx.valve.close_all()


def pull_digestor_to_meter(ctx):
    ctx.valve.close_all()
    ctx.valve.open(["消解器下阀", "消解器上阀", "计量单元入口"])
    sleep_ms(VALVE_SWITCH_STABLE_MS)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ok = wait_until(lambda: is_full(ctx.meter_optics, "大"), TIMEOUT_PULL_DIGESTOR_MS, 50)
    ctx.pump.disable()
    ctx.valve.close_all()
    return ok

