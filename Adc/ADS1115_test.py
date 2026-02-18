#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 DFRobot_ADS1115 库的连续转换模式测试程序
不再手动定义寄存器和I2C协议细节。
"""

import time
import sys
import os

# --- 引入官方库 ---
# 确保 DFRobot_ADS1115.py 文件在当前脚本目录下或 Python PATH 中
from DFRobot_ADS1115 import ADS1115

# --- 配置参数 ---
I2C_BUS = 1 # smbus2 使用的 I2C 总线号
ADS1115_ADDR = 0x48 # ADS1115 的 I2C 地址
TEST_GAIN = 8        # 增益倍数 (对应库中的 PGA 值)
TEST_CHANNEL = 0     # 测试通道 (0-3, 对应 AIN0-AIN3 vs GND)

# --- 将增益值映射到库中定义的常量 ---
GAIN_MAP = {
    1: ADS1115.REG_CONFIG_PGA_4_096V,   # 1倍 -> ±4.096V
    2: ADS1115.REG_CONFIG_PGA_2_048V,   # 2倍 -> ±2.048V
    4: ADS1115.REG_CONFIG_PGA_1_024V,   # 4倍 -> ±1.024V
    8: ADS1115.REG_CONFIG_PGA_0_512V,   # 8倍 -> ±0.512V
    16: ADS1115.REG_CONFIG_PGA_0_256V,  # 16倍 -> ±0.256V
}

def continuous_polling_with_library():
    """使用库进行连续轮询测试的主函数"""
    print(f"\n=== 使用 DFRobot_ADS1115 库的连续转换轮询测试 ===")
    print(f"测试通道: AIN{TEST_CHANNEL} vs GND")
    print(f"增益: {TEST_GAIN}x")
    print("按 Ctrl+C 停止测试")
    print("-" * 50)
    
    try:
        # 1. 创建 ADS1115 实例
        # 注意：库内部默认使用 SMBus(1)，如果需要其他总线需修改库文件
        adc = ADS1115()
        
        # 2. 设置增益
        gain_const = GAIN_MAP.get(TEST_GAIN)
        if gain_const is None:
            print(f"[ERROR] 不支持的增益值: {TEST_GAIN}. 使用默认值.")
            gain_const = ADS1115.REG_CONFIG_PGA_4_096V # 默认
        adc.set_gain(gain_const)
        print(f"[INFO] 增益已设置为 {TEST_GAIN}x")

        # 3. 设置设备地址 (如果需要)
        # adc.set_addr_ADS1115(ADS1115_ADDR) # 如果地址不是默认的0x48才需要调用

        # 4. 主循环读取
        print("时间(s)      电压(mV)")
        print("-------      --------")
        start_time = time.time()
        
        while True:
            # 4.1 读取指定通道的电压
            # 库的 read_voltage 函数内部会配置单次转换，等待并读取结果
            # 但由于我们循环调用，效果类似连续读取
            voltage_mv = adc.read_voltage(TEST_CHANNEL)['r'] # 返回值是字典 {'r': value}

            # 4.2 格式化并打印
            elapsed_time = time.time() - start_time
            
            print(f"{elapsed_time:7.2f}      {voltage_mv:>8.2f}")

            # 控制读取频率，例如每秒打印10次 (可根据需要调整)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户停止测试")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("🚀 使用 DFRobot_ADS1115 库的轮询测试程序启动")
    continuous_polling_with_library()

if __name__ == "__main__":
    main()