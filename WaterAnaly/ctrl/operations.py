"""Operation layer: compose primitive actions into process operations."""

from primitives import take, dispense, pull_digestor_to_meter, sleep_ms, aerate_stir_digestor
from config import HEAT_UP_TIMEOUT_MS


def add_to_digestor(ctx, source_name, volume):
    ok_take = take(ctx, source_name, volume)
    ok_dispense = dispense(ctx, ["消解器下阀", "消解器上阀"])
    return ok_take and ok_dispense


def rinse(ctx, source_name, waste_valve):
    ok_take = take(ctx, source_name, "小")
    ok_dispense = dispense(ctx, [waste_valve])
    return ok_take and ok_dispense


def flush_pipeline(ctx, source_name, waste_valve, times, volume):
    ok = True
    for _ in range(times):
        ok = take(ctx, source_name, volume) and ok
        ok = dispense(ctx, [waste_valve]) and ok
        sleep_ms(200)
    return ok


def empty_digestor(ctx, waste_valve):
    ok_pull = pull_digestor_to_meter(ctx)
    ok_dispense = dispense(ctx, [waste_valve])
    return ok_pull and ok_dispense


def full_clean(ctx):
    ok1 = add_to_digestor(ctx, "标一", "大")
    sleep_ms(20000)
    ok2 = empty_digestor(ctx, "废液1")
    ok3 = flush_pipeline(ctx, "标一", "废液1", 3, "大")
    return ok1 and ok2 and ok3


def heat_and_hold(temp_ctrl, target_temp, hold_ms):
    temp_ctrl.start(target_temp)
    elapsed_ms = 0
    while temp_ctrl.read_temperature() < target_temp:
        sleep_ms(500)
        # simplified timeout control
        if elapsed_ms >= HEAT_UP_TIMEOUT_MS:
            break
        elapsed_ms += 500
    temp_ctrl.hold(hold_ms)
    temp_ctrl.stop()


def read_digest_value(digest_optics, preheat_ms):
    sleep_ms(preheat_ms)
    return digest_optics.read_absorbance()


def stir_once(ctx, duration_ms):
    aerate_stir_digestor(ctx, duration_ms)
