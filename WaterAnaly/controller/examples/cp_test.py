#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于 CircuitPython 库的临时流程测试脚本
- 复刻 main.py 的流程结构
- 不依赖 controller/lib 下的库
- 顶部常量改接线即可
"""

import time

import board
import busio
import digitalio
import pwmio

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_tca9555
import adafruit_max31865
from adafruit_motor import motor


# ==================== 可配置常量 ====================
# I2C 地址
ADS1115_I2C_ADDR = 0x48
TCA9555_I2C_ADDR = 0x20

# TCA9555 功能引脚（沿用 main.py）
DISSOLVER_UP = 1
DISSOLVER_DOWN = 2
PI_DISSOLVER = 3
PI_STD_1 = 4
PI_STD_2 = 5
PI_ANL_WAST = 6

# 泵控制引脚（沿用 main.py）
PUMP_PUL_PIN = 10
PUMP_DIR_PIN = 11
PUMP_ENA_PIN = 12

# 步进参数
SUBDIVISION = 800
TARGET_RPM = 300
TARGET_FREQ = SUBDIVISION * TARGET_RPM / 60.0
HALF_PERIOD = 1.0 / (2.0 * TARGET_FREQ)

# 采样
SAMPLE_INTERVAL_SEC = 0.2
SAMPLE_LOOP_COUNT = 5

# MAX31865 / motor 临时测试
MAX31865_CS_PIN = "D5"
MOTOR_PWM_PIN_A = "D12"
MOTOR_PWM_PIN_B = "D13"
MOTOR_THROTTLE = 0.2

# 流程开关
RUN_DRAW_WATER_FLOW = True
RUN_PUSH_WATER_FLOW = True
RUN_DETECT_FLOW = True
RUN_DRAIN_FLOW = True
RUN_MAX31865_TEST = True
RUN_MOTOR_TEST = True


# ==================== 初始化 ====================
i2c = busio.I2C(board.SCL, board.SDA)

# ADS1115（用 adafruit_ads1x15）
ads = ADS.ADS1115(i2c, address=ADS1115_I2C_ADDR)
ads.gain = 1  # 约对应 4.096V 量程
ads_ch0 = AnalogIn(ads, ADS.P0)
ads_ch1 = AnalogIn(ads, ADS.P1)
ads_ch2 = AnalogIn(ads, ADS.P2)
ads_ch3 = AnalogIn(ads, ADS.P3)

# TCA9555（用 community-circuitpython-tca9555 -> adafruit_tca9555）
tca = adafruit_tca9555.TCA9555(i2c, address=TCA9555_I2C_ADDR)

# 缓存 pin 对象，避免反复申请
_tca_pin_cache = {}


def get_tca_pin(pin_no):
    if pin_no not in _tca_pin_cache:
        p = tca.get_pin(pin_no)
        p.switch_to_output(value=False)
        _tca_pin_cache[pin_no] = p
    return _tca_pin_cache[pin_no]


def pin_high(pin_no):
    get_tca_pin(pin_no).value = True


def pin_low(pin_no):
    get_tca_pin(pin_no).value = False


def close_all():
    pin_low(1)
    pin_low(2)
    pin_low(3)
    pin_low(4)
    pin_low(5)
    pin_low(6)


def ctrl_dissolver(ctrl):
    if ctrl == 1:
        pin_high(DISSOLVER_UP)
        pin_high(DISSOLVER_DOWN)
        pin_high(PI_DISSOLVER)
    else:
        pin_low(DISSOLVER_DOWN)
        pin_low(DISSOLVER_UP)
        pin_low(PI_DISSOLVER)


def pump_control(direction=1, duration_ms=3000):
    duration_sec = duration_ms / 1000.0

    print("\n=== 蠕动泵控制开始 ===")
    print(f"方向: {'正转(吸水)' if direction == 1 else '反转(排水)'}")
    print(f"运行时间: {duration_sec:.1f} 秒")
    print(f"脉冲频率: {TARGET_FREQ:.2f} Hz")

    pin_low(PUMP_PUL_PIN)
    pin_low(PUMP_DIR_PIN)
    pin_low(PUMP_ENA_PIN)
    time.sleep(0.5)

    if direction == 1:
        pin_high(PUMP_DIR_PIN)
    else:
        pin_low(PUMP_DIR_PIN)

    pin_low(PUMP_ENA_PIN)

    start_time = time.time()
    pulse_count = 0
    while (time.time() - start_time) < duration_sec:
        pin_high(PUMP_PUL_PIN)
        time.sleep(HALF_PERIOD)
        pin_low(PUMP_PUL_PIN)
        time.sleep(HALF_PERIOD)
        pulse_count += 1

    pin_high(PUMP_ENA_PIN)
    print(f"脉冲数: {pulse_count}")
    print("=== 蠕动泵控制结束 ===")


def sample_ads():
    print("\n=== ADS1115 采样开始 ===")

    count = 0
    while True:
        a0 = ads_ch0.voltage * 1000.0
        time.sleep(SAMPLE_INTERVAL_SEC)
        a1 = ads_ch1.voltage * 1000.0
        time.sleep(SAMPLE_INTERVAL_SEC)
        a2 = ads_ch2.voltage * 1000.0
        time.sleep(SAMPLE_INTERVAL_SEC)
        a3 = ads_ch3.voltage * 1000.0

        print(f"A0:{a0:.1f}mV  A1:{a1:.1f}mV  A2:{a2:.1f}mV  A3:{a3:.1f}mV")

        time.sleep(SAMPLE_INTERVAL_SEC)
        count += 1
        if SAMPLE_LOOP_COUNT >= 0 and count >= SAMPLE_LOOP_COUNT:
            break

    print("=== ADS1115 采样结束 ===")


def flow_draw_water():
    print("\n>>> 抽水流程开始")
    close_all()
    pin_high(PI_STD_1)
    input("已经打开电磁阀，按回车开始吸水 10 秒...")
    pump_control(direction=1, duration_ms=10000)
    input("按回车继续吹水 10 秒...")
    pump_control(direction=0, duration_ms=10000)
    input("按回车结束抽水流程...")
    pin_low(PI_STD_1)
    print(">>> 抽水流程结束")


def flow_push_water():
    print("\n>>> 推水流程开始")
    ctrl_dissolver(1)
    pump_control(direction=0, duration_ms=3000)
    ctrl_dissolver(0)
    print(">>> 推水流程结束")


def flow_detect():
    print("\n>>> 检测流程开始")
    sample_ads()
    print(">>> 检测流程结束")


def flow_drain():
    print("\n>>> 排水流程开始")
    ctrl_dissolver(1)
    pump_control(direction=1, duration_ms=3000)
    ctrl_dissolver(0)
    pin_high(PI_ANL_WAST)
    pump_control(direction=0, duration_ms=3000)
    pin_low(PI_ANL_WAST)
    print(">>> 排水流程结束")


def test_max31865():
    print("\n>>> MAX31865 测试开始")
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    cs = digitalio.DigitalInOut(getattr(board, MAX31865_CS_PIN))
    sensor = adafruit_max31865.MAX31865(spi, cs)
    print(f"MAX31865 温度: {sensor.temperature:.2f} C")
    print(f"MAX31865 电阻: {sensor.resistance:.2f} Ohm")
    print(">>> MAX31865 测试结束")


def test_motor():
    print("\n>>> motor 测试开始")
    pin_a = getattr(board, MOTOR_PWM_PIN_A)
    pin_b = getattr(board, MOTOR_PWM_PIN_B)

    pwm_a = pwmio.PWMOut(pin_a, frequency=1000)
    pwm_b = pwmio.PWMOut(pin_b, frequency=1000)

    dc_motor = motor.DCMotor(pwm_a, pwm_b)
    dc_motor.throttle = MOTOR_THROTTLE
    time.sleep(1.0)
    dc_motor.throttle = 0

    print(f"motor A={MOTOR_PWM_PIN_A}, B={MOTOR_PWM_PIN_B}, 油门={MOTOR_THROTTLE}")
    print(">>> motor 测试结束")


def main():
    print("开始执行 CircuitPython 库流程测试")

    if RUN_DRAW_WATER_FLOW:
        flow_draw_water()

    if RUN_PUSH_WATER_FLOW:
        flow_push_water()

    if RUN_DETECT_FLOW:
        flow_detect()

    if RUN_DRAIN_FLOW:
        flow_drain()

    if RUN_MAX31865_TEST:
        test_max31865()

    if RUN_MOTOR_TEST:
        test_motor()

    print("\n全部测试完成")


if __name__ == "__main__":
    main()
