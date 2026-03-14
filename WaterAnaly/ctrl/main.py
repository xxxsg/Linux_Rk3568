"""主流程入口。"""

from datetime import datetime
import time

from config import *
from hardware import create_hardware_context
from flow import (
    full_clean,
    rinse,
    add_to_digestor,
    flush_pipeline,
    heat_and_hold,
    stir_once,
    read_digest_value,
    empty_digestor,
)


def compute_concentration(digest_value, std2_conc):
    _ = std2_conc
    return digest_value


def run_nh3n_recipe(std2_concentration):
    ctx = create_hardware_context()
    steps = []

    def log_step(name, ok=True):
        steps.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "step": name, "ok": bool(ok)})
        print(f"[STEP] {name} -> {ok}")

    ctx.valve.close_all()

    log_step("0) 开机预清洗", full_clean(ctx))

    log_step("1a) 水样润洗", rinse(ctx, "待测溶液", "废液1"))
    log_step("1b) 水样正式加样", add_to_digestor(ctx, "待测溶液", "大"))

    log_step("2a) 标二润洗", rinse(ctx, "标二", "废液1"))
    log_step("2b) 标二加液", add_to_digestor(ctx, "标二", "大"))

    log_step("3a) 试剂A润洗", rinse(ctx, "试剂A", "废液1"))
    log_step("3b) 试剂A加液", add_to_digestor(ctx, "试剂A", "大"))
    log_step("3c) 标一冲洗2次", flush_pipeline(ctx, "标一", "废液1", 2, "大"))

    heat_and_hold(ctx.temp_ctrl, DIGEST_TEMP_C, HEAT_HOLD_MS)
    log_step("4) 加热并恒温", True)

    log_step("5a) 试剂B润洗", rinse(ctx, "试剂B", "废液1"))
    log_step("5b) 试剂B加液", add_to_digestor(ctx, "试剂B", "大"))
    log_step("5c) 标一冲洗1次", flush_pipeline(ctx, "标一", "废液1", 1, "大"))

    time.sleep((DIGEST_SETTLE_TOTAL_MS / 2) / 1000.0)
    stir_once(ctx, STIR_DURATION_MS)
    log_step("6) 静置中间通气搅拌", True)
    time.sleep((DIGEST_SETTLE_TOTAL_MS / 2) / 1000.0)

    log_step("7a) 试剂C润洗", rinse(ctx, "试剂C", "废液1"))
    log_step("7b) 试剂C加液", add_to_digestor(ctx, "试剂C", "大"))
    log_step("7c) 标一冲洗2次", flush_pipeline(ctx, "标一", "废液1", 2, "大"))

    digest_value = read_digest_value(ctx.digest_optics, OPTICS_PREHEAT_MS)
    log_step("8) 读取消解度数", True)

    concentration = compute_concentration(digest_value, std2_concentration)
    log_step("9) 浓度计算占位接口", True)

    log_step("10a) 排空消解器", empty_digestor(ctx, "废液1"))
    log_step("10b) 收尾清洗", full_clean(ctx))

    ctx.shutdown()
    result = {"digest_value": digest_value, "concentration": concentration, "steps": steps}
    print(f"[RESULT] digest_value={digest_value:.3f}, concentration={concentration:.3f}")
    return result


if __name__ == "__main__":
    run_nh3n_recipe(std2_concentration=1.0)
