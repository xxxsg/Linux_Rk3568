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

PI_DISSOLVER = 3 # 消解器
PI_STD_1 = 4 # 标准溶液1
PI_STD_2 = 5 # 标准溶液2
PI_ANL_WAST = 6 # 分析废液



def close_all():
    tca9555.set_tca9555_pin_low(1)
    tca9555.set_tca9555_pin_low(2)
    tca9555.set_tca9555_pin_low(3)
    tca9555.set_tca9555_pin_low(4)
    tca9555.set_tca9555_pin_low(5)
    tca9555.set_tca9555_pin_low(6)

def ctrl_dissolver(ctr):
    if ctr == 1:
        tca9555.set_tca9555_pin_high(DISSOLVER_UP)
        tca9555.set_tca9555_pin_high(DISSOLVER_DOWN)
        tca9555.set_tca9555_pin_high(PI_DISSOLVER)
    elif ctr == 0:
        tca9555.set_tca9555_pin_low(DISSOLVER_DOWN)
        tca9555.set_tca9555_pin_low(DISSOLVER_UP)
        tca9555.set_tca9555_pin_low(PI_DISSOLVER)


def pump_control(direction=1, duration=3000):
    """
    蠕动泵控制函数
    
    Args:
        direction (int): 运行方向，1(正转) 或 0(反转)
        duration (int): 运行时间，单位毫秒
    
    示例调用:
        pump_control(direction=1, duration=3000)  # 正转3秒吸水
        pump_control(direction=0, duration=3000)  # 反转3秒排水
    """
    # 将毫秒转换为秒
    duration_sec = duration / 1000.0
    
    print(f"=== 蠕动泵控制开始 ===")
    print(f"控制方向: {'正转(吸水)' if direction == 1 else '反转(排水)'}")
    print(f"运行时间: {duration_sec:.1f} 秒")
    print(f"脉冲频率: {TARGET_FREQ:.2f} Hz")
    print("========================")
    
    try:
        # 0. 初始化阶段：将所有相关GPIO设置为低电平
        print("\n【初始化】设置所有控制引脚为低电平...")
        tca9555.set_tca9555_pin_low(10)  # P10=PUL=0
        tca9555.set_tca9555_pin_low(11)  # P11=DIR=0
        tca9555.set_tca9555_pin_low(12)  # P12=ENA=0 (禁用状态)
        print("初始化完成，所有控制引脚已设为低电平")
        time.sleep(0.5)  # 短暂延时确保稳定
        
        # 1. 设置运行方向和使能电机
        print(f"\n【准备】设置电机方向并使能...")
        if direction == 1:
            tca9555.set_tca9555_pin_high(11)  # P11=DIR=1 (正转)
            print("方向设置: 正转(吸水)")
        else:
            tca9555.set_tca9555_pin_low(11)   # P11=DIR=0 (反转)
            print("方向设置: 反转(排水)")
        
        # 使能电机 (ENA=0)
        tca9555.set_tca9555_pin_low(12)   # P12=ENA=0 (使能)
        print("电机已使能")
        
        # 2. 发送脉冲
        print(f"\n【运行】开始{'吸水' if direction == 1 else '排水'}...")
        start_time = time.time()
        pulse_count = 0
        
        while (time.time() - start_time) < duration_sec:
            # 产生方波脉冲
            tca9555.set_tca9555_pin_high(10)  # P10=PUL=1
            time.sleep(HALF_PERIOD)
            tca9555.set_tca9555_pin_low(10)   # P10=PUL=0
            time.sleep(HALF_PERIOD)
            pulse_count += 1
        
        print(f"运行完成，脉冲数: {pulse_count}")
        
        # 3. 最终停止
        print("\n【结束】禁用电机...")
        tca9555.set_tca9555_pin_high(12)  # P12=ENA=1 (禁用)
        print("电机控制流程完成！")
        
        return True
        
    except Exception as e:
        print(f"控制过程中发生错误: {e}")
        # 确保电机安全停止
        try:
            tca9555.set_tca9555_pin_high(12)  # 禁用电机
            print("紧急停止：电机已禁用")
        except:
            pass
        return False




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

    # # 取样

    # # 抽水
    # close_all()
    # tca9555.set_tca9555_pin_high(PI_STD_1)
    # pump_control(direction=1, duration=3000)
    # tca9555.set_tca9555_pin_low(PI_STD_1)

    # time.sleep(2)

    # # 推水
    # ctrl_dissolver(1) # 打开消解器3个阀门
    # pump_control(direction=0, duration=3000)
    # ctrl_dissolver(0) # 关闭消解器3个阀门

    # # 检测
    # main()


    排水
    ctrl_dissolver(1) # 打开消解器3个阀门
    pump_control(direction=1, duration=3000)
    ctrl_dissolver(0) # 关闭消解器3个阀门
    tca9555.set_tca9555_pin_high(PI_ANL_WAST) # 打开废液
    pump_control(direction=0, duration=3000)
    tca9555.set_tca9555_pin_low(PI_ANL_WAST)
  
