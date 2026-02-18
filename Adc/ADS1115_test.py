#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的ADS1115测试程序
使用1倍增益配置
"""

import smbus2
import time
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 尝试导入DFRobot库
try:
    from DFRobot_ADS1115 import ADS1115
    USE_DFROBOT = True
    print("✅ 使用DFRobot_ADS1115库")
except ImportError:
    USE_DFROBOT = False
    print("⚠️ DFRobot_ADS1115库未找到，使用直接I2C访问")

# 配置参数
I2C_BUS = 1
ADS1115_ADDR = 0x48  # 使用i2cteset.py中的地址
TEST_GAIN = 1        # 1倍增益
TEST_CHANNEL = 0     # A0通道
TEST_SAMPLES = 5     # 测试样本数

def test_with_dfrobot():
    """使用DFRobot库进行测试"""
    print("\n=== 使用DFRobot库测试 ===")
    
    try:
        ads1115 = ADS1115()
        ads1115.set_addr_ADS1115(ADS1115_ADDR)
        ads1115.set_gain(0x02)  # 1倍增益
        
        print(f"✅ ADS1115初始化成功")
        print(f"   地址: 0x{ADS1115_ADDR:02X}")
        print(f"   增益: {TEST_GAIN}x")
        
        # 连续读取测试
        voltages = []
        for i in range(TEST_SAMPLES):
            try:
                result = ads1115.read_voltage(TEST_CHANNEL)
                voltage_mv = result['r']
                voltage_v = voltage_mv / 1000.0
                voltages.append(voltage_v)
                
                print(f"   读数 {i+1}: {voltage_v:8.4f}V ({voltage_mv}mV)")
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   读数 {i+1}: 失败 - {e}")
        
        # 统计结果
        if voltages:
            avg_v = sum(voltages) / len(voltages)
            print(f"\n📊 平均电压: {avg_v:.4f}V")
            
        return True
        
    except Exception as e:
        print(f"❌ DFRobot测试失败: {e}")
        return False

def test_with_direct_i2c():
    """直接使用I2C进行测试"""
    print("\n=== 直接I2C访问测试 ===")
    
    try:
        bus = smbus2.SMBus(I2C_BUS)
        
        # 测试设备连接
        print("1. 测试设备连接...")
        try:
            config_reg = bus.read_word_data(ADS1115_ADDR, 0x01)
            print(f"✅ 设备连接正常，配置寄存器: 0x{config_reg:04X}")
        except Exception as e:
            print(f"❌ 设备连接失败: {e}")
            bus.close()
            return False
        
        # 配置ADS1115
        print("2. 配置1倍增益...")
        try:
            # 配置寄存器: 1倍增益, A0输入, 单次转换
            config_value = 0x8583  # OS=1, MUX=100, PGA=001, MODE=1
            config_bytes = [(config_value >> 8) & 0xFF, config_value & 0xFF]
            bus.write_i2c_block_data(ADS1115_ADDR, 0x01, config_bytes)
            print(f"✅ 配置写入成功: 0x{config_value:04X}")
        except Exception as e:
            print(f"❌ 配置失败: {e}")
            bus.close()
            return False
        
        # 连续读取测试
        print("3. 连续读取测试...")
        voltages = []
        
        for i in range(TEST_SAMPLES):
            try:
                # 等待转换完成
                time.sleep(0.1)
                
                # 读取数据
                data = bus.read_i2c_block_data(ADS1115_ADDR, 0x00, 2)
                raw_adc = (data[0] << 8) | data[1]
                
                # 处理符号位
                if raw_adc > 32767:
                    raw_adc -= 65536
                
                # 转换为电压 (1倍增益: 0.125mV/bit)
                voltage_mv = raw_adc * 0.125
                voltage_v = voltage_mv / 1000.0
                voltages.append(voltage_v)
                
                print(f"   读数 {i+1}: {voltage_v:8.4f}V (原始值: {raw_adc})")
                
            except Exception as e:
                print(f"   读数 {i+1}: 失败 - {e}")
        
        bus.close()
        
        # 统计结果
        if voltages:
            avg_v = sum(voltages) / len(voltages)
            min_v = min(voltages)
            max_v = max(voltages)
            
            print(f"\n📊 测试结果:")
            print(f"   平均值: {avg_v:.4f}V")
            print(f"   最小值: {min_v:.4f}V")
            print(f"   最大值: {max_v:.4f}V")
            print(f"   波动范围: {max_v - min_v:.4f}V")
            
            # 简单评估
            if abs(avg_v) < 0.1:
                print("   📊 评估: 接近0V (可能未连接信号)")
            elif 0.5 <= abs(avg_v) <= 3.5:
                print("   📊 评估: 正常范围 (信号连接正常)")
            else:
                print("   📊 评估: 超出预期范围 (请检查连接)")
        
        return True
        
    except Exception as e:
        print(f"❌ 直接I2C测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 ADS1115简单测试程序")
    print(f"配置: 地址=0x{ADS1115_ADDR:02X}, 增益={TEST_GAIN}x, 通道=A{TEST_CHANNEL}")
    print("=" * 50)
    
    success = False
    
    # 优先使用DFRobot库
    if USE_DFROBOT:
        success = test_with_dfrobot()
    
    # 如果DFRobot失败或不可用，使用直接I2C
    if not success:
        success = test_with_direct_i2c()
    
    if success:
        print("\n🎉 测试完成!")
    else:
        print("\n❌ 测试失败!")

if __name__ == "__main__":
    main()