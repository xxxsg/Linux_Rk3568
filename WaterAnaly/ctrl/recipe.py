"""Recipe layer: NH3-N process flow built from operations."""

from datetime import datetime

from hardware import create_hardware_context
from primitives import sleep_ms
from operations import (
    full_clean,
    rinse,
    add_to_digestor,
    flush_pipeline,
    heat_and_hold,
    stir_once,
    read_digest_value,
    empty_digestor,
)
from config import (
    DIGEST_TEMP_C,
    HEAT_HOLD_MS,
    DIGEST_SETTLE_TOTAL_MS,
    STIR_DURATION_MS,
    OPTICS_PREHEAT_MS,
)


def compute_concentration(digest_value, std2_conc):
    """Placeholder concentration function for V1."""
    _ = std2_conc
    return digest_value


def run_nh3n_recipe(std2_concentration):
    ctx = create_hardware_context()
    steps = []

    def log_step(name, ok=True):
        steps.append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "step": name,
                "ok": bool(ok),
            }
        )
        print(f"[STEP] {name} -> {ok}")

    ctx.valve.close_all()

    ok = full_clean(ctx)
    log_step("0) 开机预清洗", ok)

    ok = rinse(ctx, "待测溶液", "废液1")
    log_step("1a) 水样润洗", ok)
    ok = add_to_digestor(ctx, "待测溶液", "大")
    log_step("1b) 水样正式加样", ok)

    ok = rinse(ctx, "标二", "废液1")
    log_step("2a) 标二润洗", ok)
    ok = add_to_digestor(ctx, "标二", "大")
    log_step("2b) 标二加液", ok)

    ok = rinse(ctx, "试剂A", "废液1")
    log_step("3a) 试剂A润洗", ok)
    ok = add_to_digestor(ctx, "试剂A", "大")
    log_step("3b) 试剂A加液", ok)
    ok = flush_pipeline(ctx, "标一", "废液1", 2, "大")
    log_step("3c) 标一冲洗2次", ok)

    heat_and_hold(ctx.temp_ctrl, DIGEST_TEMP_C, HEAT_HOLD_MS)
    log_step("4) 加热并恒温", True)

    ok = rinse(ctx, "试剂B", "废液1")
    log_step("5a) 试剂B润洗", ok)
    ok = add_to_digestor(ctx, "试剂B", "大")
    log_step("5b) 试剂B加液", ok)
    ok = flush_pipeline(ctx, "标一", "废液1", 1, "大")
    log_step("5c) 标一冲洗1次", ok)

    sleep_ms(DIGEST_SETTLE_TOTAL_MS // 2)
    stir_once(ctx, STIR_DURATION_MS)
    log_step("6) 静置中间通气搅拌", True)
    sleep_ms(DIGEST_SETTLE_TOTAL_MS // 2)

    ok = rinse(ctx, "试剂C", "废液1")
    log_step("7a) 试剂C润洗", ok)
    ok = add_to_digestor(ctx, "试剂C", "大")
    log_step("7b) 试剂C加液", ok)
    ok = flush_pipeline(ctx, "标一", "废液1", 2, "大")
    log_step("7c) 标一冲洗2次", ok)

    digest_value = read_digest_value(ctx.digest_optics, OPTICS_PREHEAT_MS)
    log_step("8) 读取消解度数", True)

    concentration = compute_concentration(digest_value, std2_concentration)
    log_step("9) 浓度计算占位接口", True)

    ok = empty_digestor(ctx, "废液1")
    log_step("10a) 排空消解器", ok)
    ok = full_clean(ctx)
    log_step("10b) 收尾清洗", ok)
    ctx.valve.close_all()
    ctx.shutdown()

    result = {
        "digest_value": digest_value,
        "concentration": concentration,
        "steps": steps,
    }
    print(f"[RESULT] digest_value={digest_value:.3f}, concentration={concentration:.3f}")
    return result

