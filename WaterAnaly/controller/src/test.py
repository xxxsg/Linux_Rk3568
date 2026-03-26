#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import replace
from typing import Any


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import DEFAULT_CONFIG, configure_logging
from hardware import (
    HardwareContext,
    OPTICS_CTRL_PIN_ORDER,
    VALVE_PIN_ORDER,
    build_hardware,
    cleanup_hardware,
)
from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V
from main import compute_absorbance, compute_concentration
from primitives import (
    add_to_digestor,
    close_all_valves,
    empty_digestor,
    heat_and_hold,
    read_digest_signal,
    rinse_to_waste,
)


logger = logging.getLogger(__name__)

TEST_CONFIG = replace(
    DEFAULT_CONFIG,
    logging=replace(DEFAULT_CONFIG.logging, DEBUG=True),
)

VALVE_LABELS = {
    "dissolver": "消解器主阀",
    "std_1": "标一 / 清洗液",
    "std_2": "标二",
    "sample": "样品",
    "analysis_waste": "分析废液",
    "reagent_a": "试剂 A",
    "reagent_b": "试剂 B",
    "reagent_c": "试剂 C",
    "clean_waste": "清洗废液",
    "dissolver_up": "消解器上通路",
    "dissolver_down": "消解器下通路",
}

OPTICS_LABELS = {
    "meter_up": "计量单元上液位光路",
    "meter_down": "计量单元下液位光路",
    "digest_light": "消解器光源控制",
    "digest_ref_amp": "消解器参考通道控制",
    "digest_main_amp": "消解器测量通道控制",
    "digest_heat": "消解器加热控制",
}


def wait_enter(prompt: str) -> None:
    """带中文提示的交互暂停。"""

    input(f"{prompt} 按回车继续...")


def close_all_flow_valves(ctx: HardwareContext) -> None:
    """测试流程统一关闭所有液路阀。"""

    close_all_valves(ctx)


def test_ads1115(ctx: HardwareContext) -> None:
    """读取 4 路 ADC 电压，确认 ADS1115 工作正常。"""

    ctx.ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
    logger.info("=== ADS1115 测试 ===")
    for channel in range(4):
        voltage_mv = ctx.ads1115.read_voltage(channel)
        logger.info("AIN%s = %s mV", channel, voltage_mv)


def test_max31865(ctx: HardwareContext) -> None:
    """读取温度和故障寄存器，确认温度采集链路正常。"""

    logger.info("=== MAX31865 测试 ===")
    raw_rtd = ctx.max31865.read_raw_rtd()
    resistance = ctx.max31865.read_resistance()
    fault = ctx.max31865.read_fault()
    logger.info("原始 RTD = %s", raw_rtd)
    logger.info("电阻值 = %.4f ohm", resistance)
    logger.info("故障寄存器 = 0x%02X", fault)
    try:
        temperature = ctx.max31865.read_temperature()
    except ValueError as exc:
        logger.warning("温度读取失败: %s", exc)
        return
    logger.info("温度 = %.2f C", temperature)


def test_softspi(ctx: HardwareContext) -> None:
    """检查软 SPI 与 MAX31865 的底层寄存器通信。"""

    logger.info("=== SoftSPI 测试 ===")
    logger.info("MISO 当前电平 = %s", int(ctx.spi.miso.read()))
    config_reg = ctx.max31865.read_register(0x00)
    fault_reg = ctx.max31865.read_register(0x07)
    rtd_regs = ctx.max31865.read_registers(0x01, 2)
    logger.info("CONFIG(0x00) = 0x%02X", config_reg)
    logger.info("FAULT(0x07) = 0x%02X", fault_reg)
    logger.info("RTD(0x01,0x02) = %s", [f"0x{value:02X}" for value in rtd_regs])
    ctx.spi.cs_low()
    try:
        raw_response = ctx.spi.transfer([0x00, 0x00, 0x00, 0x00])
    finally:
        ctx.spi.cs_high()
    logger.info("transfer [0x00, 0x00, 0x00, 0x00] -> %s", raw_response)


def test_tca9555_pins(ctx: HardwareContext) -> None:
    """逐个切换液路阀，便于现场确认接线与动作。"""

    logger.info("=== 液路阀测试 ===")
    for name, pin_number in VALVE_PIN_ORDER:
        pin = ctx.valves[name]
        label = VALVE_LABELS.get(name, name)
        wait_enter(f"准备打开阀门 pin {pin_number}: {label} ({name})。")
        pin.write(True)
        logger.info("已打开 pin %s: %s (%s)", pin_number, label, name)
        wait_enter(f"准备关闭阀门 pin {pin_number}: {label} ({name})。")
        pin.write(False)
        logger.info("已关闭 pin %s: %s (%s)", pin_number, label, name)


def test_optics_ctrl_pins(ctx: HardwareContext) -> None:
    """逐个切换控制类引脚，确认光路和加热控制接线。"""

    logger.info("=== 控制引脚测试 ===")
    for name, pin_number in OPTICS_CTRL_PIN_ORDER:
        pin = ctx.optics_controls[name]
        label = OPTICS_LABELS.get(name, name)
        wait_enter(f"准备拉高控制 pin {pin_number}: {label} ({name})。")
        pin.write(True)
        logger.info("已拉高 pin %s: %s (%s)", pin_number, label, name)
        wait_enter(f"准备拉低控制 pin {pin_number}: {label} ({name})。")
        pin.write(False)
        logger.info("已拉低 pin %s: %s (%s)", pin_number, label, name)


def _run_stepper_continuous(stepper: Any, direction: bool) -> None:
    """后台持续运行步进电机。"""

    stepper.run_continuous(direction=direction)


def test_pump(ctx: HardwareContext, forward_s: float = 3.0, reverse_s: float = 5.0) -> None:
    """测试泵的正转、反转和连续运转。"""

    logger.info("=== 泵测试 ===")
    logger.info("正转 %.1f 秒", forward_s)
    ctx.stepper.run_for_time(forward_s, direction=True)
    time.sleep(0.5)
    logger.info("反转 %.1f 秒", reverse_s)
    ctx.stepper.run_for_time(reverse_s, direction=False)
    time.sleep(0.5)
    logger.info("进入连续运行，按回车停止")
    worker = threading.Thread(
        target=_run_stepper_continuous,
        args=(ctx.stepper, True),
        daemon=True,
    )
    worker.start()
    try:
        input()
    finally:
        ctx.pump.emergency_stop()
        worker.join(timeout=2.0)
        logger.info("泵已停止")


def print_digest_measurement(ctx: HardwareContext) -> None:
    """读取 6 个电压，并按主流程算法打印结果。"""

    signal = read_digest_signal(ctx)
    absorbance = compute_absorbance(signal)
    concentration = compute_concentration(signal)
    logger.info("vbias_m = %.6f", signal.vbias_m)
    logger.info("vbias_r = %.6f", signal.vbias_r)
    logger.info("vm_0 = %.6f", signal.vm_0)
    logger.info("vr_0 = %.6f", signal.vr_0)
    logger.info("vm_s = %.6f", signal.vm_s)
    logger.info("vr_s = %.6f", signal.vr_s)
    logger.info("absorbance = %.6f", absorbance)
    logger.info("concentration = %.6f", concentration)


def test_flow(ctx: HardwareContext) -> None:
    """按 primitives 原语执行简化 flow 测试。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== Flow 测试 ===")

    # 步骤 1：关闭所有液路阀。
    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    # 步骤 2：用标一润洗支路并排到废液。
    wait_enter("步骤 2：用标一润洗支路并排到废液。")
    rinse_to_waste(ctx, recipe.flush_source, recipe.waste_valve)
    logger.info("步骤 2 完成：标一润洗结束")

    # 步骤 3：将标一加入消解器。
    wait_enter("步骤 3：将标一加入消解器。")
    add_to_digestor(ctx, recipe.flush_source, "large")
    logger.info("步骤 3 完成：标一已加入消解器")

    # 步骤 4：读取 6 个电压并计算浓度。
    wait_enter("步骤 4：读取 6 个电压并计算浓度。")
    print_digest_measurement(ctx)

    # 步骤 5：排空消解器到废液。
    wait_enter("步骤 5：排空消解器到废液。")
    empty_digestor(ctx, recipe.waste_valve)
    logger.info("步骤 5 完成：消解器已排空")

    # 步骤 6：关闭所有液路阀。
    wait_enter("步骤 6：关闭所有液路阀。")
    close_all_flow_valves(ctx)
    logger.info("Flow 测试完成")


def _temperature_printer(
    ctx: HardwareContext,
    stop_event: threading.Event,
    interval_s: float,
) -> None:
    """后台定时打印温度，方便观察升温过程。"""

    while not stop_event.is_set():
        try:
            temp_c = ctx.temp_sensor.read_temperature_c()
            logger.info("当前温度 = %.2f C", temp_c)
        except Exception as exc:
            logger.warning("温度读取失败: %s", exc)
        stop_event.wait(interval_s)


def test_heat(ctx: HardwareContext, target_temp_c: float = 50.0, print_interval_s: float = 3.0) -> None:
    """加热测试。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 加热测试 ===")

    # 步骤 1：关闭所有液路阀。
    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    # 步骤 2：用清洗液支路润洗并排到废液。
    wait_enter("步骤 2：用清洗液支路润洗并排到废液。")
    rinse_to_waste(ctx, recipe.clean_source, recipe.waste_valve)

    # 步骤 3：将清洗液加入消解器。
    wait_enter("步骤 3：将清洗液加入消解器。")
    add_to_digestor(ctx, recipe.clean_source, "large")
    logger.info("步骤 3 完成：测试液体已加入消解器")

    # 步骤 4：加热到目标温度，过程中持续打印温度。
    wait_enter(f"步骤 4：加热到 {target_temp_c:.1f} C，达到后立即停止。")
    stop_event = threading.Event()
    printer = threading.Thread(
        target=_temperature_printer,
        args=(ctx, stop_event, print_interval_s),
        daemon=True,
    )
    printer.start()
    try:
        heat_and_hold(ctx, target_temp_c=target_temp_c, hold_ms=0)
    finally:
        stop_event.set()
        printer.join(timeout=2.0)

    final_temp_c = ctx.temp_sensor.read_temperature_c()
    logger.info("最终温度 = %.2f C", final_temp_c)

    # 步骤 5：排空消解器。
    wait_enter("步骤 5：排空消解器到废液。")
    empty_digestor(ctx, recipe.waste_valve)
    logger.info("加热测试完成")


def run_test_by_name(ctx: HardwareContext, test_name: str) -> None:
    """按名称调度测试项。"""

    if test_name == "ads":
        test_ads1115(ctx)
    elif test_name == "spi":
        test_softspi(ctx)
    elif test_name in {"max", "max31865"}:
        test_max31865(ctx)
    elif test_name == "valves":
        test_tca9555_pins(ctx)
    elif test_name == "optics":
        test_optics_ctrl_pins(ctx)
    elif test_name == "pump":
        test_pump(ctx, forward_s=3.0, reverse_s=5.0)
    elif test_name == "flow":
        test_flow(ctx)
    elif test_name == "heat":
        test_heat(ctx)


def test() -> None:
    """测试入口。"""

    ctx = build_hardware(TEST_CONFIG)
    try:
        logger.info("硬件测试菜单已启动")
        while True:
            logger.info("")
            logger.info("可选项: ads / spi / max / valves / optics / pump / flow / heat / all / quit")
            choice = input("请输入测试项: ").strip().lower()

            if not choice:
                logger.warning("请输入一个测试项名称")
                continue

            if choice in {"quit", "exit", "q"}:
                logger.info("退出测试菜单")
                break

            if choice == "all":
                for test_name in ("ads", "spi", "max", "valves", "optics", "pump", "flow", "heat"):
                    run_test_by_name(ctx, test_name)
                continue

            if choice not in {"ads", "spi", "max", "max31865", "valves", "optics", "pump", "flow", "heat"}:
                logger.warning("未知测试项: %s", choice)
                continue

            run_test_by_name(ctx, choice)
    finally:
        cleanup_hardware(ctx)


def main() -> None:
    """测试脚本入口。"""

    configure_logging(TEST_CONFIG)
    test()


if __name__ == "__main__":
    main()
