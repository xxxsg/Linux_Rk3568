"""按需求精简后的测试入口：仅保留 4 个场景。"""

import time

from config import *
from hardware import create_hardware_context

# 交互测试参数（直接改这里）
TEST_SINGLE_VALVE_NAME = "标一"
TEST_SUCTION_MS = 3000
TEST_DISPENSE_MS = 3000


def pause(msg):
    input(msg)


def read_meter_pair(ctx, title):
    up = ctx.meter_optics.read_upper_transmittance()
    low = ctx.meter_optics.read_lower_transmittance()
    print(f"{title} -> upper={up:.2f}mV, lower={low:.2f}mV")


def test_a_single_valve(ctx):
    print("\n=== A. 测试单独开一个阀门 ===")
    pause(f"回车后关闭全部阀并打开阀门 [{TEST_SINGLE_VALVE_NAME}]...")
    ctx.valve.close_all()
    ctx.valve.open(TEST_SINGLE_VALVE_NAME)
    print(f"已打开阀门: {TEST_SINGLE_VALVE_NAME}")

    pause("回车后关闭该阀门...")
    ctx.valve.close(TEST_SINGLE_VALVE_NAME)
    print("已关闭阀门")


def test_b_temperature(ctx):
    print("\n=== B. 测试温度 ===")
    pause("回车后读取一次当前温度...")
    t = ctx.temp_ctrl.read_temperature()
    print(f"temperature={t:.2f}C")


def test_c_meter_with_suction_and_drain(ctx):
    print("\n=== C. 计量单元读数 -> 吸水 -> 读数 -> 排水 ===")

    pause("回车后读取计量单元两个读数(吸水前)...")
    read_meter_pair(ctx, "吸水前")

    pause("回车后执行吸水：待测溶液 -> 计量单元入口，泵正转...")
    ctx.valve.close_all()
    ctx.valve.open(["待测溶液", "计量单元入口"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ctx.pump.run_for(TEST_SUCTION_MS)
    ctx.pump.disable()
    ctx.valve.close_all()
    print("吸水完成")

    pause("回车后读取计量单元两个读数(吸水后)...")
    read_meter_pair(ctx, "吸水后")

    pause("回车后执行排水：计量单元 -> 废液1，泵反转...")
    ctx.valve.close_all()
    ctx.valve.open(["废液1"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    ctx.pump.run_for(TEST_DISPENSE_MS)
    ctx.pump.disable()
    ctx.valve.close_all()
    print("排水完成")


def test_d_digestor_with_fill_and_drain(ctx):
    print("\n=== D. 消解器读数 -> 吸水打到消解池 -> 读数 -> 排水 ===")

    pause("回车后读取消解器当前读数(初始)...")
    v0 = ctx.digest_optics.read_absorbance()
    print(f"消解器初始读数={v0:.2f}mV")

    pause("回车后执行吸水到计量单元：待测溶液 -> 计量单元入口...")
    ctx.valve.close_all()
    ctx.valve.open(["待测溶液", "计量单元入口"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ctx.pump.run_for(TEST_SUCTION_MS)
    ctx.pump.disable()
    ctx.valve.close_all()
    print("吸水到计量单元完成")

    pause("回车后执行打入消解池：计量单元 -> 消解器上阀+下阀...")
    ctx.valve.close_all()
    ctx.valve.open(["消解器上阀", "消解器下阀"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    ctx.pump.run_for(TEST_DISPENSE_MS)
    ctx.pump.disable()
    ctx.valve.close_all()
    print("已打入消解池")

    pause("回车后读取消解器读数(加液后)...")
    v1 = ctx.digest_optics.read_absorbance()
    print(f"消解器加液后读数={v1:.2f}mV")

    pause("回车后排水：抽取消解器 -> 计量单元，再排到废液1...")
    ctx.valve.close_all()
    ctx.valve.open(["消解器下阀", "消解器上阀", "计量单元入口"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_FORWARD)
    ctx.pump.enable()
    ctx.pump.run_for(TEST_SUCTION_MS)
    ctx.pump.disable()

    ctx.valve.close_all()
    ctx.valve.open(["废液1"])
    time.sleep(VALVE_SWITCH_STABLE_MS / 1000.0)
    ctx.pump.set_direction(DIR_REVERSE)
    ctx.pump.enable()
    ctx.pump.run_for(TEST_DISPENSE_MS)
    ctx.pump.disable()
    ctx.valve.close_all()
    print("消解器排水完成")


def test_all():
    ctx = create_hardware_context()
    try:
        test_a_single_valve(ctx)
        test_b_temperature(ctx)
        test_c_meter_with_suction_and_drain(ctx)
        test_d_digestor_with_fill_and_drain(ctx)
        print("\n全部测试场景执行完成")
    finally:
        ctx.shutdown()


if __name__ == "__main__":
    test_all()
