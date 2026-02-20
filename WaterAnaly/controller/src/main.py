#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.Lib_ADS1115 import *
from lib.TCA9555 import *

import smbus2
import time

# TCA9555引脚分配 (模拟pump_control.py的控制信号)
# P10: PUL (脉冲信号)
# P11: DIR (方向信号, 1=正转, 0=反转)
# P12: ENA (使能信号, 0=使能, 1=禁用)

# 电机参数设置
SUBDIVISION = 800       # 细分设置 (脉冲/转)
TARGET_RPM = 300        # 目标转速 (RPM)
TARGET_FREQ = (TARGET_RPM * SUBDIVISION) / 60.0  # 计算频率
PERIOD_SEC = 1.0 / TARGET_FREQ
HALF_PERIOD = PERIOD_SEC / 2.0
CONTROL_DURATION = 3.0  # 每个阶段控制时间(秒)

ads1115 = ADS1115()
tca9555 = TCA9555()

DISSOLVER_UP = 1 # 消解器通气口
DISSOLVER_DOWN = 2 # 消解器进出水口

PI_DISSOLVER = 3 # 电磁阀管道
PI_STD_1 = 4 # 标准溶液1
PI_STD_2 = 5 # 标准溶液2
PI_ANL_WAST = 6 # 分析废液



def ctrl_open():
    """
    实现与pump_control.py相同的正转-停止-反转控制逻辑
    使用TCA9555的P10/P11/P12引脚分别控制PUL/DIR/ENA信号
    """
    print("=== 开始蠕动泵控制流程 ===")
    print(f"目标转速: {TARGET_RPM} RPM")
    print(f"脉冲频率: {TARGET_FREQ:.2f} Hz")
    print(f"每个阶段时长: {CONTROL_DURATION} 秒")
    print("============================")
    
    try:
        # 1. 正转阶段
        print("\n【阶段1】开始正转...")
        # 设置方向为正转 (DIR=1)
        tca9555.set_tca9555_pin_high(11)  # P11=DIR=1 (正转)
        # 使能电机 (ENA=0)
        tca9555.set_tca9555_pin_low(12)   # P12=ENA=0 (使能)
        
        # 发送脉冲3秒
        start_time = time.time()
        pulse_count = 0
        while (time.time() - start_time) < CONTROL_DURATION:
            # 产生方波脉冲
            tca9555.set_tca9555_pin_high(10)  # P10=PUL=1
            time.sleep(HALF_PERIOD)
            tca9555.set_tca9555_pin_low(10)   # P10=PUL=0
            time.sleep(HALF_PERIOD)
            pulse_count += 1
        
        print(f"正转完成，脉冲数: {pulse_count}")
        
        # 2. 停止阶段
        print("\n【阶段2】电机停止中...")
        tca9555.set_tca9555_pin_high(12)  # P12=ENA=1 (禁用)
        time.sleep(CONTROL_DURATION)
        tca9555.set_tca9555_pin_low(12)   # P12=ENA=0 (重新使能)
        
        # 3. 反转阶段
        print("\n【阶段3】开始反转...")
        tca9555.set_tca9555_pin_low(11)   # P11=DIR=0 (反转)
        
        # 发送脉冲3秒
        start_time = time.time()
        pulse_count = 0
        while (time.time() - start_time) < CONTROL_DURATION:
            # 产生方波脉冲
            tca9555.set_tca9555_pin_high(10)  # P10=PUL=1
            time.sleep(HALF_PERIOD)
            tca9555.set_tca9555_pin_low(10)   # P10=PUL=0
            time.sleep(HALF_PERIOD)
            pulse_count += 1
        
        print(f"反转完成，脉冲数: {pulse_count}")
        
        # 4. 最终停止
        print("\n【结束】禁用电机...")
        tca9555.set_tca9555_pin_high(12)  # P12=ENA=1 (禁用)
        print("电机控制流程完成！")
        
    except Exception as e:
        print(f"控制过程中发生错误: {e}")
        # 确保电机安全停止
        tca9555.set_tca9555_pin_high(12)  # 禁用电机




def main():
    print("🚀 ADS1115 1倍增益轮询测试程序启动 (测量1-3.3V)")
    while True :
        #Set the IIC address
        ads1115.set_addr_ADS1115(0x48)
        #Sets the gain and input voltage range.
        ads1115.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
        #Get the Digital Value of Analog of selected channel
        adc0 = ads1115.read_voltage(0)
        time.sleep(0.2)
        adc1 = ads1115.read_voltage(1)
        time.sleep(0.2)
        adc2 = ads1115.read_voltage(2)
        time.sleep(0.2)
        adc3 = ads1115.read_voltage(3)
        # print("A0:%dmV A1:%dmV A2:%dmV A3:%dmV" % (adc0['r'],adc1['r'],adc2['r'],adc3['r']))
        print(f"A0:{adc0['r']}mV   A1:{adc1['r']}mV ")
        # print("adc0", adc0)
        time.sleep(0.2)

if __name__ == "__main__":
    ctrl_open()
    main()
