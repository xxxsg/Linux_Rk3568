#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADS1115连续转换模式测试程序 (原始I2C实现)
使用smbus2库直接与ADS1115通信，不依赖任何第三方ADS1115专用库。
"""

import smbus2
import time
import sys
import os

# --- 配置参数 ---
I2C_BUS = 1
ADS1115_ADDR = 0x48
TEST_GAIN = 8        # 增益
TEST_CHANNEL = 0     # 测试通道 (AIN0 vs GND)

# --- ADS1115寄存器地址 ---
REG_CONVERSION = 0x00
REG_CONFIG = 0x01

# --- 配置寄存器各字段的掩码和值 ---
# MUX (多路复用器配置) - 选择输入通道
MUX_CONFIGS = {
    0: 0x4000,  # AIN0 vs GND
    1: 0x5000,  # AIN1 vs GND
    2: 0x6000,  # AIN2 vs GND
    3: 0x7000,  # AIN3 vs GND
}

# PGA (可编程增益放大器配置)
PGA_SETTINGS = {
    0.667: 0x0000, # 0x00 << 9
    1: 0x0200,     # 0x02 << 9
    2: 0x0400,     # 0x04 << 9
    4: 0x0600,     # 0x06 << 9
    8: 0x0800,     # 0x08 << 9
    16: 0x0A00,    # 0x0A << 9
}

# MODE (工作模式) - 设为连续转换
MODE_CONTINUOUS = 0x0000 # Bit 8 = 0

# DR (数据速率) - 设为最低速8SPS以获得最高精度
DATA_RATE_8SPS = 0xE00 # Bits 7-5 = 111 (0xE << 5)

# 其他比较器相关位 (禁用)
COMP_MODE_TRADITIONAL = 0x000 # Bit 4 = 0
COMP_POL_ACTIVE_LOW = 0x000   # Bit 3 = 0
COMP_LAT_NON_LATCHING = 0x000 # Bit 2 = 0
COMP_QUE_DISABLE = 0x003      # Bits 1-0 = 11 (禁用比较器队列)

# 组合最终的连续转换配置字
CONTINUOUS_CONFIG_WORD = (
    0x8000 | # Bit 15 (OS): 写入时启动连续转换
    MUX_CONFIGS[TEST_CHANNEL] |
    PGA_SETTINGS[TEST_GAIN] |
    MODE_CONTINUOUS |
    DATA_RATE_8SPS |
    COMP_MODE_TRADITIONAL |
    COMP_POL_ACTIVE_LOW |
    COMP_LAT_NON_LATCHING |
    COMP_QUE_DISABLE
)

# 电压系数 (mV per bit)，根据增益查表
VOLTAGE_COEFFICIENT_MV = {
    0.667: 0.1875,
    1: 0.125,
    2: 0.0625,
    4: 0.03125,
    8: 0.015625,
    16: 0.0078125,
}[TEST_GAIN]

# --- 核心功能函数 ---

def configure_adc_continuous(bus, device_address, config_word):
    """
    配置ADS1115为连续转换模式
    
    Args:
        bus: smbus2.SMBus 对象
        device_address: I2C 设备地址 (e.g., 0x48)
        config_word: 16位配置字
    """
    config_bytes = [(config_word >> 8) & 0xFF, config_word & 0xFF]
    bus.write_i2c_block_data(device_address, REG_CONFIG, config_bytes)
    print(f"[INFO] 已将配置字 0x{config_word:04X} 写入到 0x{device_address:02X} 的 CONFIG 寄存器")
    print(f"[INFO] ADC配置为: 连续转换, AIN{TEST_CHANNEL}, 增益 {TEST_GAIN}x, 8SPS")

def read_raw_conversion_data(bus, device_address):
    """
    从ADS1115的CONVERSION寄存器读取原始16位数据
    
    Args:
        bus: smbus2.SMBus 对象
        device_address: I2C 设备地址 (e.g., 0x48)
    
    Returns:
        int: 16位原始数据，或 None 如果出错
    """
    try:
        # 读取2个字节的数据
        data = bus.read_i2c_block_data(device_address, REG_CONVERSION, 2)
        raw_adc = (data[0] << 8) | data[1]
        return raw_adc
    except Exception as e:
        print(f"[ERROR] 读取I2C数据失败: {e}")
        return None

def convert_raw_to_millivolts(raw_value, coefficient_mv):
    """
    将原始ADC码转换为毫伏值
    
    Args:
        raw_value: 16位原始ADC码 (可能为负数)
        coefficient_mv: 每个LSB代表的毫伏数
    
    Returns:
        float: 电压值 (mV)，或 None 如果输入为 None
    """
    if raw_value is None:
        return None
    
    # ADS1115 使用二进制补码表示有符号数
    if raw_value > 32767:
        raw_value -= 65536 # 将负数补码转换为Python的负整数
    
    voltage_mv = raw_value * coefficient_mv
    return voltage_mv

def continuous_polling_main_loop():
    """主循环：配置并持续读取数据"""
    print(f"\n=== ADS1115 连续转换轮询测试 (原始I2C) ===")
    print(f"测试通道: AIN{TEST_CHANNEL} vs GND")
    print(f"增益: {TEST_GAIN}x")
    print(f"分辨率: {VOLTAGE_COEFFICIENT_MV:.5f} mV/bit")
    print("按 Ctrl+C 停止测试")
    print("-" * 60)

    bus = None
    try:
        # 1. 初始化I2C总线
        print(f"[INFO] 正在打开 I2C 总线 {I2C_BUS} ...")
        bus = smbus2.SMBus(I2C_BUS)
        print(f"[INFO] I2C 总线 {I2C_BUS} 打开成功")

        # 2. 配置ADS1115为连续转换模式
        configure_adc_continuous(bus, ADS1115_ADDR, CONTINUOUS_CONFIG_WORD)

        # 3. 开始主循环读取
        print("\n时间(s)      原始值      电压(mV)")
        print("-------      -----      --------")
        start_time = time.time()
        
        while True:
            # 3.1 读取原始数据
            raw_value = read_raw_conversion_data(bus, ADS1115_ADDR)
            
            # 3.2 转换为电压值
            voltage_mv = convert_raw_to_millivolts(raw_value, VOLTAGE_COEFFICIENT_MV)

            # 3.3 打印结果
            elapsed_time = time.time() - start_time
            raw_str = f"{raw_value:>7}" if raw_value is not None else "  --  "
            mv_str = f"{voltage_mv:>8.2f}" if voltage_mv is not None else "  --  "
            
            print(f"{elapsed_time:7.2f}      {raw_str}      {mv_str}")

            # 3.4 控制读取频率 (例如每秒10次)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断 (Ctrl+C)，正在停止...")
    except Exception as e:
        print(f"\n\n❌  程序发生未知错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 4. 清理资源
        if bus is not None:
            print("\n[INFO] 正在关闭 I2C 总线...")
            bus.close()
            print("[INFO] I2C 总线已关闭")


def main():
    print("🚀 ADS1115 原始I2C轮询测试程序启动")
    continuous_polling_main_loop()

if __name__ == "__main__":
    main()