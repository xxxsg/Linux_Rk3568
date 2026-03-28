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
from hardware import HardwareContext, VALVE_PIN_ORDER, build_hardware, cleanup_hardware
from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V
from lib.pins import Tca9555Pin
from main import compute_absorbance, compute_concentration
from primitives import (
    add_to_digestor,
    close_all_valves,
    empty_digestor,
    heat_and_hold,
    is_meter_full,
    is_meter_empty,
    read_digest_signal,
    rinse_to_waste,
    route_meter_to_targets,
    route_source_to_meter,
    start_pump_in_background,
    wait_until,
)


logger = logging.getLogger(__name__)

TEST_CONFIG = replace(
    DEFAULT_CONFIG,
    logging=replace(DEFAULT_CONFIG.logging, DEBUG=True),
)

CONTROL_PIN_ORDER = list(TEST_CONFIG.tca.control_pins.items())

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

CONTROL_LABELS = {
    "stepper_dir": "步进电机方向控制",
    "stepper_ena": "步进电机使能控制",
    "meter_up": "计量单元上液位光路",
    "meter_down": "计量单元下液位光路",
    "digest_light": "消解器光源控制",
    "digest_ref_amp": "消解器参考通道控制",
    "digest_main_amp": "消解器测量通道控制",
    "digest_heat": "消解器加热控制",
}

TEST_ITEMS = [
    ("1", "ads", "ADS1115 四路电压读取测试"),
    ("2", "spi", "SoftSPI 与 MAX31865 寄存器通信测试"),
    ("3", "max", "MAX31865 温度采集测试"),
    ("4", "valves", "TCA9555 全部 IO 测试（valve_pins + control_pins）"),
    ("5", "valve_only", "液路阀单口测试（指定一个 IO 口）"),
    ("6", "control", "控制 IO 逐个测试（TcaConfig.control_pins 全量）"),
    ("7", "force_dispense", "强制排液测试"),
    ("8", "meter", "计量单元专项测试"),
    ("9", "meter_debug", "计量单元调试"),
    ("10", "pump", "蠕动泵正反转与连续运转测试"),
    ("11", "flow", "简化液路流程测试"),
    ("12", "heat", "加热到目标温度测试"),
    ("13", "all", "顺序执行全部自动测试项"),
    ("0", "quit", "退出测试菜单"),
]
TEST_MENU = {menu_no: (test_name, title) for menu_no, test_name, title in TEST_ITEMS}


class AbortCurrentTest(Exception):
    """用户主动退出当前测试。"""

    pass


def wait_enter(prompt: str) -> None:
    """带中文提示的交互暂停。"""

    text = input(f"{prompt} 按回车继续，输入 q 退出当前测试: ").strip().lower()
    if text == "q":
        raise AbortCurrentTest


def prompt_choice(prompt: str) -> str:
    """读取菜单输入并去掉首尾空白。"""

    return input(prompt).strip()


def prompt_optional(prompt: str) -> str:
    """读取测试过程中的输入，空表示继续，q 表示退出当前测试。"""

    text = input(prompt).strip()
    if text.lower() == "q":
        raise AbortCurrentTest
    return text


def close_all_flow_valves(ctx: HardwareContext) -> None:
    """测试流程统一关闭所有液路阀。"""

    close_all_valves(ctx)


def read_meter_voltages(
    ctx: HardwareContext,
    samples: int = 5,
    sample_gap_s: float = 0.05,
) -> list[tuple[float, float]]:
    """读取计量单元上下液位光电电压，默认连续读取 5 次。"""

    readings: list[tuple[float, float]] = []
    for index in range(samples):
        upper_mv = ctx.meter_optics.read_upper_mv()
        lower_mv = ctx.meter_optics.read_lower_mv()
        readings.append((upper_mv, lower_mv))
        if index < samples - 1:
            time.sleep(sample_gap_s)
    return readings


def log_meter_voltages(title: str, ctx: HardwareContext) -> tuple[float, float]:
    """打印计量单元 5 次原始电压，并返回最后一次读数。"""

    readings = read_meter_voltages(ctx)
    logger.info("%s", title)
    for index, (upper_mv, lower_mv) in enumerate(readings, start=1):
        logger.info("第 %s 次: 上液位 = %.3f mV, 下液位 = %.3f mV", index, upper_mv, lower_mv)
    return readings[-1]


def capture_meter_voltages(title: str, ctx: HardwareContext) -> list[tuple[float, float]]:
    """打印计量单元 5 次原始电压，并返回全部读数。"""

    readings = read_meter_voltages(ctx)
    logger.info("%s", title)
    for index, (upper_mv, lower_mv) in enumerate(readings, start=1):
        logger.info("第 %s 次: 上液位 = %.3f mV, 下液位 = %.3f mV", index, upper_mv, lower_mv)
    return readings


def _calc_transmission_percent(dark_mv: float, light_mv: float, ref_dark_mv: float, ref_light_mv: float) -> float | None:
    """按暗电压扣除后的相对光强估算透光比。"""

    ref_signal = ref_light_mv - ref_dark_mv
    cur_signal = light_mv - dark_mv
    if ref_signal <= 0:
        return None
    return cur_signal / ref_signal * 100.0


def log_meter_transmission(
    title: str,
    dry_dark_readings: list[tuple[float, float]],
    dry_light_readings: list[tuple[float, float]],
    wet_dark_readings: list[tuple[float, float]],
    wet_light_readings: list[tuple[float, float]],
) -> None:
    """逐次打印按暗电压扣除后的相对透光比。"""

    logger.info("%s", title)
    for index, (dry_dark, dry_light, wet_dark, wet_light) in enumerate(
        zip(dry_dark_readings, dry_light_readings, wet_dark_readings, wet_light_readings),
        start=1,
    ):
        upper_t = _calc_transmission_percent(dry_dark[0], dry_light[0], dry_dark[0], dry_light[0])
        lower_t = _calc_transmission_percent(dry_dark[1], dry_light[1], dry_dark[1], dry_light[1])
        wet_upper_t = _calc_transmission_percent(wet_dark[0], wet_light[0], dry_dark[0], dry_light[0])
        wet_lower_t = _calc_transmission_percent(wet_dark[1], wet_light[1], dry_dark[1], dry_light[1])
        logger.info(
            "第 %s 次: 干态上液位 = %s%%, 干态下液位 = %s%%, 吸水后上液位 = %s%%, 吸水后下液位 = %s%%",
            index,
            "100.000" if upper_t is not None else "N/A",
            "100.000" if lower_t is not None else "N/A",
            f"{wet_upper_t:.3f}" if wet_upper_t is not None else "N/A",
            f"{wet_lower_t:.3f}" if wet_lower_t is not None else "N/A",
        )


def wait_meter_light_change(
    ctx: HardwareContext,
    base_upper_mv: float,
    base_lower_mv: float,
    timeout_s: float = 3.0,
    change_threshold_mv: float = 20.0,
) -> tuple[bool, float, float]:
    """等待计量单元光源状态切换引起的电压变化。"""

    deadline = time.monotonic() + timeout_s
    latest_upper_mv = base_upper_mv
    latest_lower_mv = base_lower_mv

    while time.monotonic() < deadline:
        latest_upper_mv, latest_lower_mv = log_meter_voltages("检测光源变化中：", ctx)
        upper_changed = abs(latest_upper_mv - base_upper_mv) >= change_threshold_mv
        lower_changed = abs(latest_lower_mv - base_lower_mv) >= change_threshold_mv
        if upper_changed or lower_changed:
            return True, latest_upper_mv, latest_lower_mv

    return False, latest_upper_mv, latest_lower_mv


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
    """逐个切换 TcaConfig 里定义的全部 TCA9555 IO。"""

    logger.info("=== TCA9555 全部 IO 测试 ===")
    for name, pin_number in VALVE_PIN_ORDER:
        pin = ctx.valves[name]
        label = VALVE_LABELS.get(name, name)
        wait_enter(f"准备打开阀门 pin {pin_number}: {label} ({name})。")
        pin.write(True)
        logger.info("已打开 pin %s: %s (%s)", pin_number, label, name)
        wait_enter(f"准备关闭阀门 pin {pin_number}: {label} ({name})。")
        pin.write(False)
        logger.info("已关闭 pin %s: %s (%s)", pin_number, label, name)

    for name, pin_number in CONTROL_PIN_ORDER:
        pin = get_control_pin(ctx, name, pin_number)
        label = CONTROL_LABELS.get(name, name)
        wait_enter(f"准备拉高控制 pin {pin_number}: {label} ({name})。")
        pin.write(True)
        logger.info("已拉高 pin %s: %s (%s)", pin_number, label, name)
        wait_enter(f"准备拉低控制 pin {pin_number}: {label} ({name})。")
        pin.write(False)
        logger.info("已拉低 pin %s: %s (%s)", pin_number, label, name)


def print_valve_choices() -> None:
    """打印可选液路阀，方便单口测试时输入。"""

    logger.info("可选液路阀如下：")
    for index, (name, pin_number) in enumerate(VALVE_PIN_ORDER, start=1):
        label = VALVE_LABELS.get(name, name)
        logger.info("%s. pin %s - %s (%s)", index, pin_number, label, name)


def find_valve_pin(choice: str) -> tuple[str, int] | None:
    """支持按序号、名称或中文标签定位一个液路阀。"""

    text = choice.strip()
    if not text:
        return None

    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(VALVE_PIN_ORDER):
            return VALVE_PIN_ORDER[index - 1]

    lower_text = text.lower()
    for name, pin_number in VALVE_PIN_ORDER:
        label = VALVE_LABELS.get(name, name)
        if lower_text == name.lower() or text == label:
            return name, pin_number

    return None


def test_valve_only(ctx: HardwareContext) -> None:
    """只测试一个指定液路阀，便于现场快速点测。"""

    logger.info("=== 液路阀单口测试 ===")
    print_valve_choices()
    choice = prompt_optional("请输入要测试的阀编号 / 名称 / 中文标签，输入 q 退出当前测试: ")
    target = find_valve_pin(choice)
    if target is None:
        logger.warning("未识别的液路阀输入: %s", choice)
        return

    name, pin_number = target
    label = VALVE_LABELS.get(name, name)
    pin = ctx.valves[name]
    wait_enter(f"准备打开阀门 pin {pin_number}: {label} ({name})。")
    pin.write(True)
    logger.info("已打开 pin %s: %s (%s)", pin_number, label, name)
    wait_enter(f"准备关闭阀门 pin {pin_number}: {label} ({name})。")
    pin.write(False)
    logger.info("已关闭 pin %s: %s (%s)", pin_number, label, name)


def get_control_pin(ctx: HardwareContext, name: str, pin_number: int) -> Tca9555Pin:
    """按名称获取控制 IO，引出 stepper 相关引脚一起测试。"""

    if name in ctx.optics_controls:
        return ctx.optics_controls[name]
    return Tca9555Pin(ctx.control_io, pin_number, initial_value=False)


def test_control_pins(ctx: HardwareContext) -> None:
    """逐个切换控制类引脚，覆盖 TcaConfig 里定义的全部 control_pins。"""

    logger.info("=== 控制 IO 测试 ===")
    for name, pin_number in CONTROL_PIN_ORDER:
        pin = get_control_pin(ctx, name, pin_number)
        label = CONTROL_LABELS.get(name, name)
        wait_enter(f"准备拉高控制 pin {pin_number}: {label} ({name})。")
        pin.write(True)
        logger.info("已拉高 pin %s: %s (%s)", pin_number, label, name)
        wait_enter(f"准备拉低控制 pin {pin_number}: {label} ({name})。")
        pin.write(False)
        logger.info("已拉低 pin %s: %s (%s)", pin_number, label, name)


def test_force_dispense(ctx: HardwareContext) -> None:
    """手动持续排液，直到用户确认停止。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 强制排液测试 ===")
    logger.info("默认排向 %s (%s)", VALVE_LABELS.get(recipe.waste_valve, recipe.waste_valve), recipe.waste_valve)

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：建立计量单元到废液的通路。")
    route_meter_to_targets(ctx, [recipe.waste_valve])
    logger.info("已切换到排液通路")

    prompt_optional("步骤 3：直接按回车开始强制排液，输入 q 退出当前测试: ")
    worker = start_pump_in_background(ctx.pump.dispense_continuous)
    logger.info("强制排液中，回车停止，输入 q 也会停止并退出当前测试")
    try:
        prompt_optional("")
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_flow_valves(ctx)
        logger.info("强制排液已停止，液路阀已关闭")


def test_meter_unit(ctx: HardwareContext) -> None:
    """计量单元专项测试：不开灯电压、开灯电压、吸水自动停止。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 计量单元专项测试 ===")

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：关闭计量单元上下光路灯，读取不开灯电压。")
    ctx.optics_controls["meter_up"].write(False)
    ctx.optics_controls["meter_down"].write(False)
    dark_upper_mv, dark_lower_mv = log_meter_voltages("不开灯电压：", ctx)

    wait_enter("步骤 3：打开计量单元上下光路灯，读取开灯电压。")
    ctx.optics_controls["meter_up"].write(True)
    ctx.optics_controls["meter_down"].write(True)
    changed, light_upper_mv, light_lower_mv = wait_meter_light_change(
        ctx,
        dark_upper_mv,
        dark_lower_mv,
        timeout_s=3.0,
    )
    logger.info("开灯阶段最后一次读数：上液位 = %.3f mV, 下液位 = %.3f mV", light_upper_mv, light_lower_mv)
    if not changed:
        logger.warning("3 秒内未检测到计量单元光源变化，停止当前专项测试")
        ctx.optics_controls["meter_up"].write(False)
        ctx.optics_controls["meter_down"].write(False)
        close_all_flow_valves(ctx)
        return

    wait_enter("步骤 4：开始样品吸水，验证计量单元到位后是否自动停止。")
    route_source_to_meter(ctx, recipe.sample_source)
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    try:
        ok = wait_until(
            lambda: is_meter_full(ctx, "large"),
            TEST_CONFIG.timing.take_large_timeout_ms,
            poll_ms=50,
        )
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_flow_valves(ctx)

    if ok:
        logger.info("吸水测试结果：已检测到计量单元到位，泵已自动停止")
    else:
        logger.warning("吸水测试结果：在超时时间内未检测到计量单元到位")

    log_meter_voltages("吸水测试结束后的电压：", ctx)

    wait_enter("步骤 5：如需把计量单元液体排空，请准备继续。")
    route_meter_to_targets(ctx, [recipe.waste_valve])
    worker = start_pump_in_background(ctx.pump.dispense_continuous)
    try:
        empty_ok = wait_until(
            lambda: is_meter_empty(ctx),
            TEST_CONFIG.timing.dispense_timeout_ms,
            poll_ms=50,
        )
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_flow_valves(ctx)
        ctx.optics_controls["meter_up"].write(False)
        ctx.optics_controls["meter_down"].write(False)

    if empty_ok:
        logger.info("计量单元排空完成")
    else:
        logger.warning("计量单元排空超时，请现场确认液路状态")


def test_meter_debug(ctx: HardwareContext) -> None:
    """计量单元调试：干态/吸水后分别读取关灯与开灯电压。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 计量单元调试 ===")

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：未吸水且未开灯，读取 5 次电压。")
    ctx.optics_controls["meter_up"].write(False)
    ctx.optics_controls["meter_down"].write(False)
    dry_dark_readings = capture_meter_voltages("干态未开灯电压：", ctx)

    wait_enter("步骤 3：未吸水但开灯，读取 5 次电压。")
    ctx.optics_controls["meter_up"].write(True)
    ctx.optics_controls["meter_down"].write(True)
    dry_light_readings = capture_meter_voltages("干态开灯电压：", ctx)

    wait_enter("步骤 4：按样品通路吸水 3 秒。")
    route_source_to_meter(ctx, recipe.sample_source)
    try:
        ctx.pump.aspirate_time(3.0)
    finally:
        close_all_flow_valves(ctx)

    wait_enter("步骤 5：吸水后先关灯，读取 5 次电压。")
    ctx.optics_controls["meter_up"].write(False)
    ctx.optics_controls["meter_down"].write(False)
    wet_dark_readings = capture_meter_voltages("吸水后未开灯电压：", ctx)

    wait_enter("步骤 6：吸水后开灯，读取 5 次电压。")
    ctx.optics_controls["meter_up"].write(True)
    ctx.optics_controls["meter_down"].write(True)
    wet_light_readings = capture_meter_voltages("吸水后开灯电压：", ctx)

    log_meter_transmission(
        "按暗电压扣除后的相对透光比：",
        dry_dark_readings,
        dry_light_readings,
        wet_dark_readings,
        wet_light_readings,
    )

    wait_enter("步骤 7：将计量单元液体排到废液。")
    route_meter_to_targets(ctx, [recipe.waste_valve])
    worker = start_pump_in_background(ctx.pump.dispense_continuous)
    try:
        empty_ok = wait_until(
            lambda: is_meter_empty(ctx),
            TEST_CONFIG.timing.dispense_timeout_ms,
            poll_ms=50,
        )
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_flow_valves(ctx)

    if empty_ok:
        logger.info("计量单元调试排水完成")
    else:
        logger.warning("计量单元调试排水超时，请现场确认液路状态")

    ctx.optics_controls["meter_up"].write(False)
    ctx.optics_controls["meter_down"].write(False)


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
    logger.info("进入连续运行，按回车停止，输入 q 也会停止并退出当前测试")
    worker = threading.Thread(
        target=_run_stepper_continuous,
        args=(ctx.stepper, True),
        daemon=True,
    )
    worker.start()
    try:
        prompt_optional("")
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

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：用标一润洗支路并排到废液。")
    rinse_to_waste(ctx, recipe.flush_source, recipe.waste_valve)
    logger.info("步骤 2 完成：标一润洗结束")

    wait_enter("步骤 3：将标一加入消解器。")
    add_to_digestor(ctx, recipe.flush_source, "large")
    logger.info("步骤 3 完成：标一已加入消解器")

    wait_enter("步骤 4：读取 6 个电压并计算浓度。")
    print_digest_measurement(ctx)

    wait_enter("步骤 5：排空消解器到废液。")
    empty_digestor(ctx, recipe.waste_valve)
    logger.info("步骤 5 完成：消解器已排空")

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

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：用清洗液支路润洗并排到废液。")
    rinse_to_waste(ctx, recipe.clean_source, recipe.waste_valve)

    wait_enter("步骤 3：将清洗液加入消解器。")
    add_to_digestor(ctx, recipe.clean_source, "large")
    logger.info("步骤 3 完成：测试液体已加入消解器")

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
    elif test_name == "valve_only":
        test_valve_only(ctx)
    elif test_name in {"control", "optics"}:
        test_control_pins(ctx)
    elif test_name == "force_dispense":
        test_force_dispense(ctx)
    elif test_name == "meter":
        test_meter_unit(ctx)
    elif test_name == "meter_debug":
        test_meter_debug(ctx)
    elif test_name == "pump":
        test_pump(ctx, forward_s=3.0, reverse_s=5.0)
    elif test_name == "flow":
        test_flow(ctx)
    elif test_name == "heat":
        test_heat(ctx)


def run_test_with_guard(ctx: HardwareContext, test_name: str, title: str) -> None:
    """统一处理当前测试被用户中断的情况。"""

    try:
        logger.info("")
        run_test_by_name(ctx, test_name)
    except AbortCurrentTest:
        logger.warning("已退出当前测试：%s", title)
    finally:
        try:
            ctx.pump.stop()
        except Exception:
            pass
        try:
            close_all_flow_valves(ctx)
        except Exception:
            pass
        try:
            ctx.optics_controls["meter_up"].write(False)
            ctx.optics_controls["meter_down"].write(False)
        except Exception:
            pass


def test() -> None:
    """测试入口。"""

    ctx = build_hardware(TEST_CONFIG)
    try:
        logger.info("硬件测试菜单已启动")
        while True:
            logger.info("")
            logger.info("请选择测试项目：")
            for menu_no, _, title in TEST_ITEMS:
                logger.info("%s. %s", menu_no, title)

            choice = prompt_choice("请输入数字编号: ")
            if not choice:
                logger.warning("请输入一个数字编号")
                continue

            menu_item = TEST_MENU.get(choice)
            if menu_item is None:
                logger.warning("未知菜单编号: %s", choice)
                continue

            test_name, title = menu_item
            if test_name == "quit":
                logger.info("退出测试菜单")
                break

            logger.info("开始执行：%s", title)
            if test_name == "all":
                for _, batch_test_name, batch_title in TEST_ITEMS:
                    if batch_test_name in {"all", "quit", "valve_only"}:
                        if batch_test_name == "valve_only":
                            logger.info("跳过液路阀单口测试，该项需要现场指定阀口")
                        continue
                    run_test_with_guard(ctx, batch_test_name, batch_title)
                logger.info("全部自动测试项执行完成")
                continue

            run_test_with_guard(ctx, test_name, title)
    finally:
        cleanup_hardware(ctx)


def main() -> None:
    """测试脚本入口。"""

    configure_logging(TEST_CONFIG)
    test()


if __name__ == "__main__":
    main()
