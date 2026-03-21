#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

"""硬件联调脚本。

这个文件主要用于单独验证板上各个硬件是否工作正常，
适合在主流程联调前做快速排查。

包含的测试项：
1. ADS1115 模拟量采集测试
2. MAX31865 温度采集测试
3. TCA9555 阀门引脚开关测试
4. 步进泵正反转、连续运行和急停测试
"""

import os
import sys
import threading
import time
from typing import Any, Dict


# 允许直接从 src 目录运行时导入上一级 lib。
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from lib.ADS1115 import ADS1115, ADS1115_REG_CONFIG_PGA_4_096V
from lib.MAX31865 import MAX31865
from lib.SoftSPI import SoftSPI
from lib.TCA9555 import TCA9555
from lib.pins import GpiodPin, Tca9555Pin
from lib.pump import Pump
from lib.stepper import Stepper


# TCA9555 所在 I2C 总线编号。
TCA9555_BUS = 1
# TCA9555 设备地址。
TCA9555_ADDR = 0x20
# 第二颗 TCA9555 设备地址（用于步进驱动控制）。
TCA9555_CTRL_ADDR = 0x21
# ADS1115 所在 I2C 总线编号。
ADS1115_BUS = 1
# ADS1115 设备地址。
ADS1115_ADDR = 0x48

# TCA9555 输出引脚定义。
# 这些命名和业务液路名称保持一致，便于流程代码直接复用。
# PIN_DISSOLVER：消解器主阀。
PIN_DISSOLVER = 0
# PIN_STD_1：标液 1 阀门。
PIN_STD_1 = 1
# PIN_STD_2：标液 2 阀门。
PIN_STD_2 = 2
# PIN_SAMPLE：样品阀门。
PIN_SAMPLE = 3
# PIN_ANALYSIS_WASTE：分析废液阀门。
PIN_ANALYSIS_WASTE = 4
# PIN_REAGENT_A：试剂 A 阀门。
PIN_REAGENT_A = 5
# PIN_REAGENT_B：试剂 B 阀门。
PIN_REAGENT_B = 6
# PIN_REAGENT_C：试剂 C 阀门。
PIN_REAGENT_C = 7
# PIN_CLEAN_WASTE：清洗废液阀门。
PIN_CLEAN_WASTE = 8
# PIN_DISSOLVER_UP：消解器上游阀门。
PIN_DISSOLVER_UP = 9
# PIN_DISSOLVER_DOWN：消解器下游阀门。
PIN_DISSOLVER_DOWN = 10
# PIN_STEPPER_DIR：步进驱动方向控制引脚（0x21 pin0）。
PIN_STEPPER_DIR = 0
# PIN_STEPPER_ENA：步进驱动使能控制引脚（0x21 pin1）。
PIN_STEPPER_ENA = 1

# 步进驱动器的脉冲输出引脚，直接由 GPIO 输出。
# 元组格式为 `(gpiochip 路径, line 编号)`。
GPIO_STEPPER_PUL = ("/dev/gpiochip1", 1)

# MAX31865 软 SPI 的各个引脚定义。
# GPIO_MAX31865_SCLK：SPI 时钟线。 pin2
GPIO_MAX31865_SCLK = ("/dev/gpiochip3", 5)
# GPIO_MAX31865_MOSI：SPI 主发从收数据线。 pin3
GPIO_MAX31865_MOSI = ("/dev/gpiochip1", 0)
# GPIO_MAX31865_MISO：SPI 主收从发数据线。pin4
GPIO_MAX31865_MISO = ("/dev/gpiochip3", 4)
# GPIO_MAX31865_CS：MAX31865 片选信号线。 pin5
GPIO_MAX31865_CS = ("/dev/gpiochip3", 3)

# 阀门遍历顺序，供交互式测试逐个开关。
VALVE_PIN_ORDER = [
    # ("业务名称", 对应的 TCA9555 pin 编号)
    ("dissolver", PIN_DISSOLVER),
    ("std_1", PIN_STD_1),
    ("std_2", PIN_STD_2),
    ("sample", PIN_SAMPLE),
    ("analysis_waste", PIN_ANALYSIS_WASTE),
    ("reagent_a", PIN_REAGENT_A),
    ("reagent_b", PIN_REAGENT_B),
    ("reagent_c", PIN_REAGENT_C),
    ("clean_waste", PIN_CLEAN_WASTE),
    ("dissolver_up", PIN_DISSOLVER_UP),
    ("dissolver_down", PIN_DISSOLVER_DOWN),
]


def close_all_flow_valves(hw: Dict[str, Any]) -> None:
    """关闭流程相关阀门。

    参数：
        hw: `init_hardware()` 返回的硬件字典。

    说明：
        这里优先使用 TCA9555 的整字写入能力，一次性关闭流程阀门。
        仅处理 pin 0~10 这批流程阀门，不去改动步进驱动的 DIR/ENA 状态。
    """

    valve_mask = 0
    for _, pin_number in VALVE_PIN_ORDER:
        valve_mask |= 1 << pin_number

    current_output = hw["tca9555"].output_state
    new_output = current_output & ~valve_mask
    hw["tca9555"].write_word(new_output)


def init_hardware() -> Dict[str, Any]:
    """初始化测试所需的全部硬件对象。

    返回：
        Dict[str, Any]:
            统一返回一个硬件字典，包含：
            - `tca9555`：TCA9555 IO 扩展器对象
            - `ads1115`：ADS1115 模数转换器对象
            - `valves`：阀门引脚对象字典，key 为业务名称
            - `stepper`：底层步进驱动对象
            - `pump`：基于 Stepper 的泵控制对象
            - `spi`：MAX31865 使用的 SoftSPI 对象
            - `max31865`：温度采集对象
    """

    # 初始化 IO 扩展器，用于控制阀门和步进驱动的部分控制脚。
    tca9555 = TCA9555(i2c_bus=TCA9555_BUS, addr=TCA9555_ADDR)
    tca9555_ctrl = TCA9555(i2c_bus=TCA9555_BUS, addr=TCA9555_CTRL_ADDR)
    # 初始化 ADS1115，用于读取模拟量。
    ads1115 = ADS1115(i2c_bus=ADS1115_BUS, addr=ADS1115_ADDR)

    valve_pins: Dict[str, Tca9555Pin] = {}
    valve_pins["dissolver"] = Tca9555Pin(tca9555, PIN_DISSOLVER, initial_value=False)
    valve_pins["std_1"] = Tca9555Pin(tca9555, PIN_STD_1, initial_value=False)
    valve_pins["std_2"] = Tca9555Pin(tca9555, PIN_STD_2, initial_value=False)
    valve_pins["sample"] = Tca9555Pin(tca9555, PIN_SAMPLE, initial_value=False)
    valve_pins["analysis_waste"] = Tca9555Pin(tca9555, PIN_ANALYSIS_WASTE, initial_value=False)
    valve_pins["reagent_a"] = Tca9555Pin(tca9555, PIN_REAGENT_A, initial_value=False)
    valve_pins["reagent_b"] = Tca9555Pin(tca9555, PIN_REAGENT_B, initial_value=False)
    valve_pins["reagent_c"] = Tca9555Pin(tca9555, PIN_REAGENT_C, initial_value=False)
    valve_pins["clean_waste"] = Tca9555Pin(tca9555, PIN_CLEAN_WASTE, initial_value=False)
    valve_pins["dissolver_up"] = Tca9555Pin(tca9555, PIN_DISSOLVER_UP, initial_value=False)
    valve_pins["dissolver_down"] = Tca9555Pin(tca9555, PIN_DISSOLVER_DOWN, initial_value=False)

    # pul_pin：步进驱动脉冲脚，每发一个脉冲代表前进一步。
    pul_pin = GpiodPin(
        GPIO_STEPPER_PUL,
        consumer="test_stepper_pul",
        default_value=False,
    )
    # dir_pin：控制步进驱动方向。
    dir_pin = Tca9555Pin(tca9555_ctrl, PIN_STEPPER_DIR, initial_value=False)
    # ena_pin：控制步进驱动使能。
    ena_pin = Tca9555Pin(tca9555_ctrl, PIN_STEPPER_ENA, initial_value=True)

    stepper = Stepper(
        # pul_pin：脉冲输出引脚。
        pul_pin=pul_pin,
        # dir_pin：方向控制引脚。
        dir_pin=dir_pin,
        # ena_pin：使能控制引脚。
        ena_pin=ena_pin,
        # steps_per_rev：每转一圈对应的脉冲步数。
        steps_per_rev=800,
    )
    stepper.configure_driver(
        # dir_high_forward=True：DIR 为高电平时定义为正向。
        dir_high_forward=True,
        # ena_low_enable=True：ENA 为低电平时驱动器使能。
        ena_low_enable=True,
        # auto_enable=True：运动开始前自动使能，结束后自动失能。
        auto_enable=True,
    )
    # set_rpm(300)：设置目标转速为 300 RPM。
    stepper.set_rpm(300)

    # aspirate_direction="reverse"：把反向定义为吸液方向。
    pump = Pump(driver=stepper, aspirate_direction="reverse")

    spi = SoftSPI(
        # sclk：SPI 时钟线。
        sclk=GpiodPin(
            GPIO_MAX31865_SCLK,
            consumer="test_max31865_sclk",
            default_value=False,
        ),
        # mosi：主设备输出到从设备输入的数据线。
        mosi=GpiodPin(
            GPIO_MAX31865_MOSI,
            consumer="test_max31865_mosi",
            default_value=False,
        ),
        # miso：主设备输入、从设备输出的数据线。
        miso=GpiodPin(
            GPIO_MAX31865_MISO,
            consumer="test_max31865_miso",
            mode="input",
        ),
        # cs：片选线，拉低时选中 MAX31865。
        cs=GpiodPin(
            GPIO_MAX31865_CS,
            consumer="test_max31865_cs",
            default_value=True,
        ),
    )
    max31865 = MAX31865(
        # spi：上面构造好的 SoftSPI 对象。
        spi=spi,
        # rref：参考电阻阻值。
        rref=430.0,
        # r0：RTD 在 0°C 时的标称阻值，PT100 对应 100 欧。
        r0=100.0,
        # wires：探头接线数，这里使用 2 线制。
        wires=2,
        # filter_frequency：工频滤波频率，这里按 50Hz 设置。
        filter_frequency=50,
    )

    return {
        "tca9555": tca9555,
        "tca9555_ctrl": tca9555_ctrl,
        "ads1115": ads1115,
        "valves": valve_pins,
        "stepper": stepper,
        "pump": pump,
        "spi": spi,
        "max31865": max31865,
    }


def cleanup_hardware(hw: Dict[str, Any]) -> None:
    """释放测试脚本创建的硬件资源。

    参数：
        hw: `init_hardware()` 返回的硬件字典。
            如果传入空字典或 None 风格的值，则直接返回。
    """

    if not hw:
        return

    ads1115 = hw.get("ads1115")
    if ads1115 is not None:
        try:
            ads1115.close()
        except Exception:
            pass

    max31865 = hw.get("max31865")
    if max31865 is not None:
        try:
            max31865.close()
        except Exception:
            pass

    pump = hw.get("pump")
    if pump is not None:
        try:
            pump.cleanup()
        except Exception:
            pass

    for pin in hw.get("valves", {}).values():
        try:
            pin.close()
        except Exception:
            pass

    tca9555 = hw.get("tca9555")
    if tca9555 is not None:
        try:
            tca9555.close()
        except Exception:
            pass

    tca9555_ctrl = hw.get("tca9555_ctrl")
    if tca9555_ctrl is not None:
        try:
            tca9555_ctrl.close()
        except Exception:
            pass


def test_ads1115(hw: Dict[str, Any]) -> None:
    """测试 ADS1115 四个通道的电压读取。

    参数：
        hw: `init_hardware()` 返回的硬件字典，
            其中必须包含 `ads1115`。
    """

    ads1115 = hw["ads1115"]
    ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)

    print("=== ADS1115 电压读取测试 ===")
    for channel in range(4):
        voltage_mv = ads1115.read_voltage(channel)
        print(f"AIN{channel}: {voltage_mv} mV")


def test_max31865(hw: Dict[str, Any]) -> None:
    """测试 MAX31865 的温度、阻值和故障状态读取。

    参数：
        hw: `init_hardware()` 返回的硬件字典，
            其中必须包含 `max31865`。
    """

    max31865 = hw["max31865"]

    print("=== MAX31865 温度读取测试 ===")
    raw_rtd = max31865.read_raw_rtd()
    resistance = max31865.read_resistance()
    fault = max31865.read_fault()

    print(f"原始RTD: {raw_rtd}")
    print(f"阻值: {resistance:.4f} ohm")
    print(f"故障寄存器: 0x{fault:02X}")

    try:
        temperature = max31865.read_temperature()
    except ValueError as exc:
        print(f"温度换算失败: {exc}")
        print("这通常表示PT100/PT1000未接好、线制配置不匹配，或SPI读取异常。")
        return

    print(f"温度: {temperature:.2f} C")


def test_softspi(hw: Dict[str, Any]) -> None:
    """直接测试 SoftSPI 与 MAX31865 的底层寄存器读写。"""

    spi = hw["spi"]
    max31865 = hw["max31865"]

    print("=== SoftSPI 原始通信测试 ===")
    print(f"MISO 空闲电平: {int(spi.miso.read())}")

    config_reg = max31865.read_register(0x00)
    fault_reg = max31865.read_register(0x07)
    rtd_regs = max31865.read_registers(0x01, 2)

    print(f"CONFIG(0x00): 0x{config_reg:02X}")
    print(f"FAULT(0x07): 0x{fault_reg:02X}")
    print(f"RTD(0x01,0x02): {[f'0x{value:02X}' for value in rtd_regs]}")

    # 手动做一次原始 SPI 事务，便于确认 CS/SCLK/MOSI/MISO 时序是否正常。
    spi.cs_low()
    try:
        raw_response = spi.transfer([0x00, 0x00, 0x00, 0x00])
    finally:
        spi.cs_high()
    print(f"原始事务 [0x00, 0x00, 0x00, 0x00] -> {raw_response}")


def test_tca9555_pins(hw: Dict[str, Any]) -> None:
    """逐个手动测试阀门输出引脚。

    参数：
        hw: `init_hardware()` 返回的硬件字典，
            其中必须包含 `valves`。

    说明：
        每次打开或关闭一个阀门前都会等待用户按回车，
        方便现场观察继电器或阀门动作是否正常。
    """

    valves = hw["valves"]

    print("=== TCA9555 Pin 逐个输出测试 ===")
    for name, pin_number in VALVE_PIN_ORDER:
        pin = valves[name]
        input(f"按回车打开 pin {pin_number}: {name}")
        pin.write(True)
        print(f"已打开 pin {pin_number}: {name}")
        input(f"按回车关闭 pin {pin_number}: {name}")
        pin.write(False)
        print(f"已关闭 pin {pin_number}: {name}")


def _run_stepper_continuous(stepper: Stepper, direction: bool) -> None:
    """后台线程中的连续转动函数。

    参数：
        stepper: 步进驱动对象。
        direction: 方向布尔值。
            - True：一个方向
            - False：反向
    """

    stepper.run_continuous(direction=direction)


def test_pump(hw: Dict[str, Any], forward_s: float = 3.0, reverse_s: float = 5.0) -> None:
    """测试泵的正转、反转和连续运行急停。

    参数：
        hw: `init_hardware()` 返回的硬件字典，
            其中必须包含 `stepper` 和 `pump`。
        forward_s: 正向运行时间，单位秒。
        reverse_s: 反向运行时间，单位秒。
    """

    stepper = hw["stepper"]
    pump = hw["pump"]

    print("=== Pump 运行测试 ===")
    print(f"正转 {forward_s:.1f}s")
    stepper.run_for_time(forward_s, direction=True)

    time.sleep(0.5)

    print(f"反转 {reverse_s:.1f}s")
    stepper.run_for_time(reverse_s, direction=False)

    time.sleep(0.5)

    print("开始连续运行，按回车执行急停...")
    worker = threading.Thread(
        target=_run_stepper_continuous,
        args=(stepper, True),
        daemon=True,
    )
    worker.start()

    try:
        input()
    finally:
        pump.emergency_stop()
        worker.join(timeout=2.0)
        print("已执行急停")


def test_flow(
    hw: Dict[str, Any],
    aspirate_to_meter_s: float = 3.0,
    dispense_to_digestor_s: float = 5.0,
    pull_from_digestor_s: float = 3.0,
    waste_drain_s: float = 3.0,
) -> None:
    """执行一次简化流程测试。

    参数：
        hw: `init_hardware()` 返回的硬件字典。
        aspirate_to_meter_s: 第 2 步吸液到计量端游的时长，单位秒。
        dispense_to_digestor_s: 第 4 步向消解器吹液的时长，单位秒。
        pull_from_digestor_s: 第 7 步从消解器吸液的时长，单位秒。
        waste_drain_s: 第 5、8 步排到分析废液的时长，单位秒。

    说明：
        由于第 7、8 步原始描述没有明确时长，这里默认按 3 秒处理。
    """

    ads1115 = hw["ads1115"]
    valves = hw["valves"]
    pump = hw["pump"]

    digestor_valves = ["dissolver", "dissolver_up", "dissolver_down"]
    waste_valve = "analysis_waste"

    print("=== 流程测试开始 ===")

    input("步骤1: 关闭所有阀门，按回车继续...")
    close_all_flow_valves(hw)
    time.sleep(0.5)

    input(f"步骤2: 打开标1阀门并吸液 {aspirate_to_meter_s:.1f}s，液体进入计量端游，按回车继续...")
    valves["std_1"].write(True)
    pump.aspirate_time(aspirate_to_meter_s)
    valves["std_1"].write(False)
    time.sleep(0.5)

    input("步骤3: 打开消解器相关阀门（3个），按回车继续...")
    for name in digestor_valves:
        valves[name].write(True)
    time.sleep(0.5)

    input(f"步骤4: 向消解器吹液 {dispense_to_digestor_s:.1f}s，按回车继续...")
    pump.dispense_time(dispense_to_digestor_s)
    time.sleep(0.5)

    input("步骤5: 关闭消解器阀门，打开分析废液排液，然后关闭分析废液阀门，按回车继续...")
    for name in digestor_valves:
        valves[name].write(False)
    valves[waste_valve].write(True)
    pump.dispense_time(waste_drain_s)
    valves[waste_valve].write(False)
    time.sleep(0.5)

    input("步骤6: 读取 ADS1115 4 路数值，按回车继续...")
    ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
    for channel in range(4):
        voltage_mv = ads1115.read_voltage(channel)
        print(f"AIN{channel}: {voltage_mv} mV")
    time.sleep(0.5)

    input(f"步骤7: 打开消解器阀门，再次吸液 {pull_from_digestor_s:.1f}s，按回车继续...")
    for name in digestor_valves:
        valves[name].write(True)
    pump.aspirate_time(pull_from_digestor_s)
    time.sleep(0.5)

    input("步骤8: 关闭消解器阀门，打开分析废液排液，然后关闭分析废液阀门，按回车继续...")
    for name in digestor_valves:
        valves[name].write(False)
    valves[waste_valve].write(True)
    pump.dispense_time(waste_drain_s)
    valves[waste_valve].write(False)

    input("流程测试结束，关闭所有阀门，按回车完成...")
    close_all_flow_valves(hw)


def run_test_by_name(hw: Dict[str, Any], test_name: str) -> None:
    """按名称分发单项测试。

    参数：
        hw: `init_hardware()` 返回的硬件字典。
        test_name: 测试名称。
            支持：
            - `ads`
            - `spi`
            - `max`
            - `valves`
            - `pump`
            - `flow`
    """

    if test_name == "ads":
        test_ads1115(hw)
    elif test_name == "spi":
        test_softspi(hw)
    elif test_name in {"max", "max31865"}:
        test_max31865(hw)
    elif test_name == "valves":
        test_tca9555_pins(hw)
    elif test_name == "pump":
        test_pump(hw, forward_s=3.0, reverse_s=5.0)
    elif test_name == "flow":
        test_flow(hw)


def test() -> None:
    """交互式联调入口。

    说明：
        启动后通过命令行输入测试项名称，
        逐项验证当前硬件工作状态。
    """

    hw = init_hardware()
    try:
        print("硬件测试环境已初始化")
        while True:
            print("")
            print("可选测试项: ads / spi / max / valves / pump / flow / all / quit")
            choice = input("请输入要执行的测试项: ").strip().lower()

            if not choice:
                print("输入为空，请重新输入")
                continue

            if choice in {"quit", "exit", "q"}:
                print("退出测试")
                break

            if choice == "all":
                for test_name in ("ads", "spi", "max", "valves", "pump", "flow"):
                    run_test_by_name(hw, test_name)
                continue

            if choice not in {"ads", "spi", "max", "max31865", "valves", "pump", "flow"}:
                print(f"不支持的测试项: {choice}")
                continue

            run_test_by_name(hw, choice)
    finally:
        cleanup_hardware(hw)


def main() -> None:
    """脚本入口函数。"""

    test()


if __name__ == "__main__":
    main()
