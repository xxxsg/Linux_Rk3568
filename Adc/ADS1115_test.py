#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import smbus2
import time
import sys
import os
from Lib_ADS1115 import *

# --- 配置参数 ---
I2C_BUS = 1
ADS1115_ADDR = 0x48
TEST_GAIN = 1        # 新增：1倍增益配置
TEST_CHANNEL = 0     # 测试通道 (AIN0 vs GND)

# 组合最终的连续转换配置字
CONTINUOUS_CONFIG_WORD = (

)

ads1115 = ADS1115()




def main():
    print("🚀 ADS1115 1倍增益轮询测试程序启动 (测量1-3.3V)")
    while True :
        #Set the IIC address
        ads1115.set_addr_ADS1115(0x48)
        #Sets the gain and input voltage range.
        ads1115.set_gain(ADS1115_REG_CONFIG_PGA_0_512V)
        #Get the Digital Value of Analog of selected channel
        adc0 = ads1115.read_voltage(0)
        time.sleep(0.2)
        adc1 = ads1115.read_voltage(1)
        time.sleep(0.2)
        adc2 = ads1115.read_voltage(2)
        time.sleep(0.2)
        adc3 = ads1115.read_voltage(3)
        print("A0:%dmV A1:%dmV A2:%dmV A3:%dmV" % (adc0['r'],adc1['r'],adc2['r'],adc3['r']))
        print("adc0", adc0)
        time.sleep(0.2)

if __name__ == "__main__":
    main()