#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import replace


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import DEFAULT_CONFIG, configure_logging
from hardware import HardwareContext, VALVE_PIN_ORDER, build_hardware, cleanup_hardware
from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V
from main import compute_absorbance, compute_concentration
from primitives import (
    RecipeError,
    add_to_digestor,
    close_all_valves,
    empty_digestor,
    heat_and_hold,
    is_meter_full,
    is_meter_empty,
    pull_digestor_to_meter,
    read_digest_signal,
    route_meter_to_targets,
    route_source_to_meter,
    start_pump_in_background,
    wait_until,
)


logger = logging.getLogger(__name__)

TEST_CONFIG = replace(
    DEFAULT_CONFIG,
    logging=replace(DEFAULT_CONFIG.logging, DEBUG=DEFAULT_CONFIG.logging.DEBUG),
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
    ("1", "ads", "ADS1115 四路电压读取"),
    ("2", "spi", "SoftSPI 寄存器通信"),
    ("3", "max", "MAX31865 温度采集"),
    ("4", "valves", "TCA9555 全部 IO 测试"),
    ("5", "control", "控制 IO 逐个测试"),
    ("6", "valve_high", "液路阀单口设置为高电平"),
    ("7", "valve_low", "液路阀单口设置为低电平"),
    ("8", "meter_aspirate_manual", "吸液到计量单元（回车停止）"),
    ("9", "force_dispense", "强制排液（回车停止）"),
    ("10", "set_all_low_except_pul", "临时：除 PUL 外所有引脚置低"),
    ("11", "meter_light_off", "计量单元 - 关灯测电压"),
    ("12", "meter_light_on", "计量单元 - 开灯测电压"),
    ("13", "meter_aspirate_small", "计量单元 - 吸水自动停止（少量）"),
    ("14", "meter_aspirate_large", "计量单元 - 吸水自动停止（大量）"),
    ("21", "digest_add", "消解 - 吸水到消解器"),
    ("22", "digest_pull", "消解 - 从消解器回抽"),
    ("23", "heat_short", "消解 - 加热 30 秒"),
    ("24", "heat_to_target", "消解 - 加热到 50°C"),
    ("25", "digest_read", "消解 - 完整读数"),
    ("0", "quit", "退出"),
]
TEST_MENU = {menu_no: (test_name, title) for menu_no, test_name, title in TEST_ITEMS}

# 批量执行时跳过的交互项
INTERACTIVE_TESTS = {"valve_high", "valve_low", "meter_aspirate_manual", "force_dispense"}


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


def _trimmed_mean(values: list[float]) -> float:
    """去最大最小后求平均。"""

    if len(values) <= 2:
        return sum(values) / len(values)
    sorted_vals = sorted(values)
    return sum(sorted_vals[1:-1]) / (len(sorted_vals) - 2)


def capture_meter_voltages(title: str, ctx: HardwareContext) -> list[tuple[float, float]]:
    """打印计量单元 5 次原始电压（上下分开），并返回全部读数。"""

    readings = read_meter_voltages(ctx)
    upper_vals = [r[0] for r in readings]
    lower_vals = [r[1] for r in readings]

    logger.info("%s", title)
    logger.info("--- 上液位 ---")
    for index, mv in enumerate(upper_vals, start=1):
        logger.info("第 %s 次: %.3f mV", index, mv)
    logger.info("去最大最小平均: %.3f mV", _trimmed_mean(upper_vals))

    logger.info("--- 下液位 ---")
    for index, mv in enumerate(lower_vals, start=1):
        logger.info("第 %s 次: %.3f mV", index, mv)
    logger.info("去最大最小平均: %.3f mV", _trimmed_mean(lower_vals))

    return readings


# ==================== 基础测试 (1-5) ====================

def test_ads1115(ctx: HardwareContext) -> None:
    """读取 4 路 ADC 电压，确认 ADS1115 工作正常。"""

    ctx.ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
    logger.info("=== ADS1115 测试 ===")
    for channel in range(4):
        voltage_mv = ctx.ads1115.read_voltage(channel)
        logger.info("AIN%s = %s mV", channel, voltage_mv)


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

    for name, pin in ctx.optics_controls.items():
        label = CONTROL_LABELS.get(name, name)
        wait_enter(f"准备拉高控制 {label} ({name})。")
        pin.write(True)
        logger.info("已拉高 %s: %s", label, name)
        wait_enter(f"准备拉低控制 {label} ({name})。")
        pin.write(False)
        logger.info("已拉低 %s: %s", label, name)


def test_control_pins(ctx: HardwareContext) -> None:
    """逐个切换控制类引脚，覆盖 optics_controls 里的全部控制引脚。"""

    logger.info("=== 控制 IO 测试 ===")
    for name, pin in ctx.optics_controls.items():
        label = CONTROL_LABELS.get(name, name)
        wait_enter(f"准备拉高控制 {label} ({name})。")
        pin.write(True)
        logger.info("已拉高 %s: %s", label, name)
        wait_enter(f"准备拉低控制 {label} ({name})。")
        pin.write(False)
        logger.info("已拉低 %s: %s", label, name)


# ==================== 单阀测试 (6-7) ====================

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


def test_valve_high(ctx: HardwareContext) -> None:
    """选一个液路阀，设置为高电平后自动关闭。"""

    logger.info("=== 液路阀单口置高测试 ===")
    print_valve_choices()
    choice = prompt_optional("请输入阀编号 / 名称 / 中文标签，输入 q 退出: ")
    target = find_valve_pin(choice)
    if target is None:
        logger.warning("未识别的液路阀输入: %s", choice)
        return

    name, pin_number = target
    label = VALVE_LABELS.get(name, name)
    pin = ctx.valves[name]
    try:
        pin.write(True)
        logger.info("已将 pin %s: %s (%s) 设置为高电平", pin_number, label, name)
        wait_enter(f"pin {pin_number}: {label} 当前为高电平")
    finally:
        pin.write(False)
        logger.info("已关闭 pin %s: %s (%s)", pin_number, label, name)


def test_valve_low(ctx: HardwareContext) -> None:
    """选一个液路阀，设置为低电平。"""

    logger.info("=== 液路阀单口置低测试 ===")
    print_valve_choices()
    choice = prompt_optional("请输入阀编号 / 名称 / 中文标签，输入 q 退出: ")
    target = find_valve_pin(choice)
    if target is None:
        logger.warning("未识别的液路阀输入: %s", choice)
        return

    name, pin_number = target
    label = VALVE_LABELS.get(name, name)
    pin = ctx.valves[name]
    pin.write(False)
    logger.info("已将 pin %s: %s (%s) 设置为低电平", pin_number, label, name)


def test_set_all_low_except_pul(ctx: HardwareContext) -> None:
    """临时调试：除 PUL 原生 GPIO 外，所有 GpiodPin 输出引脚置低。"""

    logger.info("=== 临时：除 PUL 外所有 GpiodPin 置低 ===")
    # SoftSPI 的输出引脚置低（跳过 MISO 输入引脚）
    ctx.spi.sclk.low()
    logger.info("SPI SCLK -> 低")
    ctx.spi.mosi.low()
    logger.info("SPI MOSI -> 低")
    ctx.spi.cs.low()
    logger.info("SPI CS -> 低")
    logger.info("完成：PUL 和 MISO（输入）保持不变，其余 GpiodPin 输出引脚均已置低")


# ==================== 手动泵测试 (8-9) ====================

def test_meter_aspirate_manual(ctx: HardwareContext) -> None:
    """从样品液源吸液到计量单元，回车停止。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 吸液到计量单元（手动停止）===")
    logger.info("液源: %s (%s)", VALVE_LABELS.get(recipe.sample_source, recipe.sample_source), recipe.sample_source)

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：建立液源到计量单元的通路。")
    route_source_to_meter(ctx, recipe.sample_source)
    logger.info("已切换到吸液通路")

    prompt_optional("步骤 3：直接按回车开始吸液，输入 q 退出: ")
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    logger.info("吸液中，回车停止，输入 q 也会停止")
    try:
        prompt_optional("")
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_flow_valves(ctx)
        logger.info("吸液已停止，液路阀已关闭")


def test_force_dispense(ctx: HardwareContext) -> None:
    """手动持续排液，直到用户确认停止。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 强制排液（回车停止）===")
    logger.info("默认排向 %s (%s)", VALVE_LABELS.get(recipe.waste_valve, recipe.waste_valve), recipe.waste_valve)

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：建立计量单元到废液的通路。")
    route_meter_to_targets(ctx, [recipe.waste_valve])
    logger.info("已切换到排液通路")

    prompt_optional("步骤 3：直接按回车开始排液，输入 q 退出: ")
    worker = start_pump_in_background(ctx.pump.dispense_continuous)
    logger.info("排液中，回车停止，输入 q 也会停止")
    try:
        prompt_optional("")
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)
        close_all_flow_valves(ctx)
        logger.info("排液已停止，液路阀已关闭")


# ==================== 计量单元测试 (11-14) ====================

def test_meter_light_off(ctx: HardwareContext) -> None:
    """关闭计量单元光路，读取电压。"""

    logger.info("=== 计量单元 - 关灯测电压 ===")
    ctx.optics_controls["meter_up"].write(False)
    ctx.optics_controls["meter_down"].write(False)
    capture_meter_voltages("关灯电压：", ctx)
    wait_enter("关灯电压已读取")


def test_meter_light_on(ctx: HardwareContext) -> None:
    """打开计量单元光路，读取电压。"""

    logger.info("=== 计量单元 - 开灯测电压 ===")
    ctx.optics_controls["meter_up"].write(True)
    ctx.optics_controls["meter_down"].write(True)
    capture_meter_voltages("开灯电压：", ctx)
    ctx.optics_controls["meter_up"].write(False)
    ctx.optics_controls["meter_down"].write(False)
    wait_enter("开灯电压已读取")


def _aspirate_with_ratio(ctx, volume, timeout_ms):
    """吸水并持续打印电压比值，到位或超时自动停止。"""

    # 1. 读取基准电压（空管开灯状态）
    upper_base = ctx.meter_optics.read_upper_mv()
    lower_base = ctx.meter_optics.read_lower_mv()
    logger.info("基准电压: 上液位 = %.3f mV, 下液位 = %.3f mV", upper_base, lower_base)

    # 2. 启动泵
    worker = start_pump_in_background(ctx.pump.aspirate_continuous)
    threshold_pct = TEST_CONFIG.thresholds.voltage_change_percent
    deadline = time.monotonic() + timeout_ms / 1000.0

    try:
        while time.monotonic() < deadline:
            upper_mv = ctx.meter_optics.read_upper_mv()
            lower_mv = ctx.meter_optics.read_lower_mv()
            upper_ratio = upper_mv / upper_base if upper_base != 0 else 0
            lower_ratio = lower_mv / lower_base if lower_base != 0 else 0
            logger.info("上液位 = %.3f mV (比值 %.4f), 下液位 = %.3f mV (比值 %.4f)",
                        upper_mv, upper_ratio, lower_mv, lower_ratio)
            # 电压上升超过阈值百分比视为到位
            upper_rise = (upper_mv - upper_base) / upper_base * 100 if upper_base != 0 else 0
            lower_rise = (lower_mv - lower_base) / lower_base * 100 if lower_base != 0 else 0
            if volume == "large":
                if lower_rise >= threshold_pct:
                    logger.info("检测到液位到位（下液位上升 %.2f%%），停止吸水", lower_rise)
                    return True
            else:
                if upper_rise >= threshold_pct:
                    logger.info("检测到液位到位（上液位上升 %.2f%%），停止吸水", upper_rise)
                    return True
            time.sleep(0.5)
    finally:
        ctx.pump.stop()
        worker.join(timeout=2.0)

    logger.warning("吸水超时（%ds），未检测到计量单元到位", timeout_ms // 1000)
    return False


def test_meter_aspirate_small(ctx: HardwareContext) -> None:
    """少量吸水到计量单元，验证到位自动停止。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 计量单元 - 吸水自动停止（少量）===")
    logger.info("液源: %s (%s)", VALVE_LABELS.get(recipe.sample_source, recipe.sample_source), recipe.sample_source)

    wait_enter("准备开始少量吸水测试。")
    close_all_flow_valves(ctx)
    ctx.optics_controls["meter_up"].write(True)
    ctx.optics_controls["meter_down"].write(True)
    try:
        route_source_to_meter(ctx, recipe.sample_source)
        ok = _aspirate_with_ratio(ctx, "small", 15_000)
    finally:
        close_all_flow_valves(ctx)
        ctx.optics_controls["meter_up"].write(False)
        ctx.optics_controls["meter_down"].write(False)

    if ok:
        logger.info("少量吸水完成")
    else:
        logger.warning("少量吸水超时")


def test_meter_aspirate_large(ctx: HardwareContext) -> None:
    """大量吸水到计量单元，验证到位自动停止。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 计量单元 - 吸水自动停止（大量）===")
    logger.info("液源: %s (%s)", VALVE_LABELS.get(recipe.sample_source, recipe.sample_source), recipe.sample_source)

    wait_enter("准备开始大量吸水测试。")
    close_all_flow_valves(ctx)
    ctx.optics_controls["meter_up"].write(True)
    ctx.optics_controls["meter_down"].write(True)
    try:
        route_source_to_meter(ctx, recipe.sample_source)
        ok = _aspirate_with_ratio(ctx, "large", 15_000)
    finally:
        close_all_flow_valves(ctx)
        ctx.optics_controls["meter_up"].write(False)
        ctx.optics_controls["meter_down"].write(False)

    if ok:
        logger.info("大量吸水完成")
    else:
        logger.warning("大量吸水超时")


# ==================== 消解器测试 (21-25) ====================

def test_digest_add(ctx: HardwareContext) -> None:
    """吸水到消解器。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 消解 - 吸水到消解器 ===")
    logger.info("液源: %s (%s)", VALVE_LABELS.get(recipe.sample_source, recipe.sample_source), recipe.sample_source)

    wait_enter("准备将液体加入消解器。")
    close_all_flow_valves(ctx)
    try:
        add_to_digestor(ctx, recipe.sample_source, "large")
        logger.info("液体已加入消解器")
    except RecipeError as exc:
        logger.warning("加液失败: %s", exc)
    finally:
        close_all_flow_valves(ctx)


def test_digest_pull(ctx: HardwareContext) -> None:
    """从消解器回抽到计量单元。"""

    logger.info("=== 消解 - 从消解器回抽 ===")

    wait_enter("准备从消解器回抽液体。")
    close_all_flow_valves(ctx)
    try:
        pull_digestor_to_meter(ctx)
        logger.info("回抽完成")
    except RecipeError as exc:
        logger.warning("回抽失败: %s", exc)
    finally:
        close_all_flow_valves(ctx)


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


def test_heat_short(ctx: HardwareContext) -> None:
    """加热 30 秒。"""

    recipe = TEST_CONFIG.recipe
    logger.info("=== 消解 - 加热 30 秒 ===")

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：将清洗液加入消解器。")
    try:
        add_to_digestor(ctx, recipe.clean_source, "large")
        logger.info("测试液体已加入消解器")
    except RecipeError as exc:
        logger.warning("加液失败: %s", exc)
        return

    wait_enter("步骤 3：开始加热 30 秒。")
    stop_event = threading.Event()
    printer = threading.Thread(
        target=_temperature_printer,
        args=(ctx, stop_event, 3.0),
        daemon=True,
    )
    printer.start()
    try:
        heat_and_hold(ctx, target_temp_c=recipe.digest_target_temp_c, hold_ms=30_000)
    except RecipeError as exc:
        logger.warning("加热异常: %s", exc)
    finally:
        stop_event.set()
        printer.join(timeout=2.0)

    final_temp_c = ctx.temp_sensor.read_temperature_c()
    logger.info("最终温度 = %.2f C", final_temp_c)

    wait_enter("步骤 4：排空消解器到废液。")
    try:
        empty_digestor(ctx, recipe.waste_valve)
        logger.info("消解器已排空")
    except RecipeError as exc:
        logger.warning("排空失败: %s", exc)


def test_heat_to_target(ctx: HardwareContext) -> None:
    """加热到 50°C。"""

    recipe = TEST_CONFIG.recipe
    target_temp_c = 50.0
    logger.info("=== 消解 - 加热到 %.1f°C ===", target_temp_c)

    wait_enter("步骤 1：关闭所有液路阀。")
    close_all_flow_valves(ctx)

    wait_enter("步骤 2：将清洗液加入消解器。")
    try:
        add_to_digestor(ctx, recipe.clean_source, "large")
        logger.info("测试液体已加入消解器")
    except RecipeError as exc:
        logger.warning("加液失败: %s", exc)
        return

    wait_enter(f"步骤 3：加热到 {target_temp_c:.1f}°C。")
    stop_event = threading.Event()
    printer = threading.Thread(
        target=_temperature_printer,
        args=(ctx, stop_event, 3.0),
        daemon=True,
    )
    printer.start()
    try:
        heat_and_hold(ctx, target_temp_c=target_temp_c, hold_ms=0)
    except RecipeError as exc:
        logger.warning("加热异常: %s", exc)
    finally:
        stop_event.set()
        printer.join(timeout=2.0)

    final_temp_c = ctx.temp_sensor.read_temperature_c()
    logger.info("最终温度 = %.2f C", final_temp_c)

    wait_enter("步骤 4：排空消解器到废液。")
    try:
        empty_digestor(ctx, recipe.waste_valve)
        logger.info("消解器已排空")
    except RecipeError as exc:
        logger.warning("排空失败: %s", exc)


def test_digest_read(ctx: HardwareContext) -> None:
    """读取 6 个电压，并按主流程算法打印结果。"""

    logger.info("=== 消解 - 完整读数 ===")
    signal = read_digest_signal(ctx)
    logger.info("vbias_m = %.6f", signal.vbias_m)
    logger.info("vbias_r = %.6f", signal.vbias_r)
    logger.info("vm_0 = %.6f", signal.vm_0)
    logger.info("vr_0 = %.6f", signal.vr_0)
    logger.info("vm_s = %.6f", signal.vm_s)
    logger.info("vr_s = %.6f", signal.vr_s)
    try:
        absorbance = compute_absorbance(signal)
        concentration = compute_concentration(signal)
        logger.info("absorbance = %.6f", absorbance)
        logger.info("concentration = %.6f", concentration)
    except (ValueError, ZeroDivisionError) as exc:
        logger.warning("吸光度/浓度计算失败: %s（消解器可能无样品或光路未准备好）", exc)
    wait_enter("读数已完毕")


# ==================== 调度与安全收尾 ====================

def run_test_by_name(ctx: HardwareContext, test_name: str) -> None:
    """按名称调度测试项。"""

    dispatch = {
        "ads": test_ads1115,
        "spi": test_softspi,
        "max": test_max31865,
        "valves": test_tca9555_pins,
        "control": test_control_pins,
        "valve_high": test_valve_high,
        "valve_low": test_valve_low,
        "set_all_low_except_pul": test_set_all_low_except_pul,
        "meter_aspirate_manual": test_meter_aspirate_manual,
        "force_dispense": test_force_dispense,
        "meter_light_off": test_meter_light_off,
        "meter_light_on": test_meter_light_on,
        "meter_aspirate_small": test_meter_aspirate_small,
        "meter_aspirate_large": test_meter_aspirate_large,
        "digest_add": test_digest_add,
        "digest_pull": test_digest_pull,
        "heat_short": test_heat_short,
        "heat_to_target": test_heat_to_target,
        "digest_read": test_digest_read,
    }
    fn = dispatch.get(test_name)
    if fn is None:
        logger.warning("未知测试项: %s", test_name)
        return
    fn(ctx)


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
                    if batch_test_name in {"all", "quit"}:
                        continue
                    if batch_test_name in INTERACTIVE_TESTS:
                        logger.info("跳过交互测试项：%s", batch_title)
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
