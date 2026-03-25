#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from hardware import (
    HardwareContext,
    OPTICS_CTRL_PIN_ORDER,
    VALVE_PIN_ORDER,
    build_hardware,
    cleanup_hardware,
)
from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V


VALVE_LABELS = {
    "dissolver": "消解器主阀",
    "std_1": "标一/清洗液阀",
    "std_2": "标二阀",
    "sample": "水样阀",
    "analysis_waste": "分析废液阀",
    "reagent_a": "试剂 A 阀",
    "reagent_b": "试剂 B 阀",
    "reagent_c": "试剂 C 阀",
    "clean_waste": "清洗废液阀",
    "dissolver_up": "消解器上通路阀",
    "dissolver_down": "消解器下通路阀",
}

OPTICS_LABELS = {
    "meter_up": "计量上位光路控制",
    "meter_down": "计量下位光路控制",
    "digest_light": "消解读数光源控制",
    "digest_ref_amp": "消解参考通道控制",
    "digest_main_amp": "消解测量通道控制",
}


def close_all_flow_valves(ctx: HardwareContext) -> None:
    ctx.valve.close_all()


def test_ads1115(ctx: HardwareContext) -> None:
    ctx.ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)

    print("=== ADS1115 读数测试 ===")
    for channel in range(4):
        voltage_mv = ctx.ads1115.read_voltage(channel)
        print(f"AIN{channel}: {voltage_mv} mV")


def test_max31865(ctx: HardwareContext) -> None:
    print("=== MAX31865 读数测试 ===")
    raw_rtd = ctx.max31865.read_raw_rtd()
    resistance = ctx.max31865.read_resistance()
    fault = ctx.max31865.read_fault()

    print(f"原始 RTD: {raw_rtd}")
    print(f"电阻值: {resistance:.4f} ohm")
    print(f"故障寄存器: 0x{fault:02X}")

    try:
        temperature = ctx.max31865.read_temperature()
    except ValueError as exc:
        print(f"温度读取失败: {exc}")
        return

    print(f"温度: {temperature:.2f} C")


def test_softspi(ctx: HardwareContext) -> None:
    print("=== SoftSPI 测试 ===")
    print(f"MISO 电平: {int(ctx.spi.miso.read())}")

    config_reg = ctx.max31865.read_register(0x00)
    fault_reg = ctx.max31865.read_register(0x07)
    rtd_regs = ctx.max31865.read_registers(0x01, 2)

    print(f"CONFIG(0x00): 0x{config_reg:02X}")
    print(f"FAULT(0x07): 0x{fault_reg:02X}")
    print(f"RTD(0x01,0x02): {[f'0x{value:02X}' for value in rtd_regs]}")

    ctx.spi.cs_low()
    try:
        raw_response = ctx.spi.transfer([0x00, 0x00, 0x00, 0x00])
    finally:
        ctx.spi.cs_high()
    print(f"原始传输 [0x00, 0x00, 0x00, 0x00] -> {raw_response}")


def test_tca9555_pins(ctx: HardwareContext) -> None:
    print("=== 液路阀逐个测试 ===")
    for name, pin_number in VALVE_PIN_ORDER:
        pin = ctx.valves[name]
        label = VALVE_LABELS.get(name, name)
        input(f"按回车打开 pin {pin_number}: {label} ({name})")
        pin.write(True)
        print(f"已打开 pin {pin_number}: {label} ({name})")
        input(f"按回车关闭 pin {pin_number}: {label} ({name})")
        pin.write(False)
        print(f"已关闭 pin {pin_number}: {label} ({name})")


def test_optics_ctrl_pins(ctx: HardwareContext) -> None:
    print("=== 光路控制逐个测试 ===")
    for name, pin_number in OPTICS_CTRL_PIN_ORDER:
        pin = ctx.optics_controls[name]
        label = OPTICS_LABELS.get(name, name)
        input(f"按回车打开 pin {pin_number}: {label} ({name})")
        pin.write(True)
        print(f"已打开 pin {pin_number}: {label} ({name})")
        input(f"按回车关闭 pin {pin_number}: {label} ({name})")
        pin.write(False)
        print(f"已关闭 pin {pin_number}: {label} ({name})")


def _run_stepper_continuous(stepper: Any, direction: bool) -> None:
    stepper.run_continuous(direction=direction)


def test_pump(ctx: HardwareContext, forward_s: float = 3.0, reverse_s: float = 5.0) -> None:
    print("=== Pump 测试 ===")
    print(f"正转 {forward_s:.1f}s")
    ctx.stepper.run_for_time(forward_s, direction=True)

    time.sleep(0.5)

    print(f"反转 {reverse_s:.1f}s")
    ctx.stepper.run_for_time(reverse_s, direction=False)

    time.sleep(0.5)

    print("连续运转中，按回车停止...")
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
        print("已停止")


def test_flow(
    ctx: HardwareContext,
    aspirate_to_meter_s: float = 3.0,
    dispense_to_digestor_s: float = 5.0,
    pull_from_digestor_s: float = 3.0,
    waste_drain_s: float = 3.0,
) -> None:
    digestor_valves = ["dissolver", "dissolver_up", "dissolver_down"]
    waste_valve = "analysis_waste"

    print("=== 液路主路径测试 ===")

    input("步骤1: 全关液路阀，按回车继续...")
    close_all_flow_valves(ctx)
    time.sleep(0.5)

    input(f"步骤2: 打开 std_1 并吸液 {aspirate_to_meter_s:.1f}s，按回车继续...")
    ctx.valves["std_1"].write(True)
    ctx.pump.aspirate_time(aspirate_to_meter_s)
    ctx.valves["std_1"].write(False)
    time.sleep(0.5)

    input("步骤3: 打开消解器相关阀，按回车继续...")
    for name in digestor_valves:
        ctx.valves[name].write(True)
    time.sleep(0.5)

    input(f"步骤4: 向消解器排液 {dispense_to_digestor_s:.1f}s，按回车继续...")
    ctx.pump.dispense_time(dispense_to_digestor_s)
    time.sleep(0.5)

    input("步骤5: 切到废液并排液，按回车继续...")
    for name in digestor_valves:
        ctx.valves[name].write(False)
    ctx.valves[waste_valve].write(True)
    ctx.pump.dispense_time(waste_drain_s)
    ctx.valves[waste_valve].write(False)
    time.sleep(0.5)

    input("步骤6: 读取 ADS1115 四路电压，按回车继续...")
    ctx.ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
    for channel in range(4):
        voltage_mv = ctx.ads1115.read_voltage(channel)
        print(f"AIN{channel}: {voltage_mv} mV")
    time.sleep(0.5)

    input(f"步骤7: 再次打开消解器阀并回抽 {pull_from_digestor_s:.1f}s，按回车继续...")
    for name in digestor_valves:
        ctx.valves[name].write(True)
    ctx.pump.aspirate_time(pull_from_digestor_s)
    time.sleep(0.5)

    input("步骤8: 再次排到废液，按回车继续...")
    for name in digestor_valves:
        ctx.valves[name].write(False)
    ctx.valves[waste_valve].write(True)
    ctx.pump.dispense_time(waste_drain_s)
    ctx.valves[waste_valve].write(False)

    input("测试结束，按回车关闭所有液路阀...")
    close_all_flow_valves(ctx)


def run_test_by_name(ctx: HardwareContext, test_name: str) -> None:
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


def test() -> None:
    ctx = build_hardware()
    try:
        print("硬件测试菜单")
        while True:
            print("")
            print("可选项: ads / spi / max / valves / optics / pump / flow / all / quit")
            choice = input("请输入选项: ").strip().lower()

            if not choice:
                print("请输入有效选项")
                continue

            if choice in {"quit", "exit", "q"}:
                print("退出测试")
                break

            if choice == "all":
                for test_name in ("ads", "spi", "max", "valves", "optics", "pump", "flow"):
                    run_test_by_name(ctx, test_name)
                continue

            if choice not in {"ads", "spi", "max", "max31865", "valves", "optics", "pump", "flow"}:
                print(f"不支持的测试项: {choice}")
                continue

            run_test_by_name(ctx, choice)
    finally:
        cleanup_hardware(ctx)


def main() -> None:
    test()


if __name__ == "__main__":
    main()
