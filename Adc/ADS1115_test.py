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
TEST_DURATION = 1.0  # 测试持续时间(秒)

# 校准参数
OFFSET_CALIBRATION = 0.0  # 偏移校准值(伏特)

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
                # 应用偏移校准
                calibrated_voltage = voltage_v + OFFSET_CALIBRATION
                voltages.append(calibrated_voltage)
                
                print(f"   读数 {i+1}: {calibrated_voltage:8.4f}V ({voltage_mv}mV, 校准:{OFFSET_CALIBRATION:+.4f}V)")
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
                # 应用偏移校准
                calibrated_voltage = voltage_v + OFFSET_CALIBRATION
                voltages.append(calibrated_voltage)
                
                print(f"   读数 {i+1}: {calibrated_voltage:8.4f}V (原始:{voltage_v:8.4f}V, 校准:{OFFSET_CALIBRATION:+.4f}V)")
                
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
            
            # 显示校准信息
            if abs(OFFSET_CALIBRATION) > 0.001:
                print(f"   ⚙️  当前偏移校准: {OFFSET_CALIBRATION:+.4f}V")
        
        return True
        
    except Exception as e:
        print(f"❌ 直接I2C测试失败: {e}")
        return False

def continuous_test_1s():
    """1秒钟连续测试功能"""
    print("\n=== 1秒钟连续测试 ===")
    print(f"开始连续采样 {TEST_DURATION} 秒...")
    
    try:
        bus = smbus2.SMBus(I2C_BUS)
        
        # 配置ADS1115
        config_value = 0x8583  # 1倍增益, A0输入, 单次转换
        config_bytes = [(config_value >> 8) & 0xFF, config_value & 0xFF]
        bus.write_i2c_block_data(ADS1115_ADDR, 0x01, config_bytes)
        
        readings = []
        start_time = time.time()
        sample_count = 0
        
        # 连续采样1秒钟
        while (time.time() - start_time) < TEST_DURATION:
            try:
                # 等待转换完成
                time.sleep(0.01)  # 10ms间隔
                
                # 读取数据
                data = bus.read_i2c_block_data(ADS1115_ADDR, 0x00, 2)
                raw_adc = (data[0] << 8) | data[1]
                
                # 处理符号位
                if raw_adc > 32767:
                    raw_adc -= 65536
                
                # 转换为电压
                voltage_mv = raw_adc * 0.125
                voltage_v = voltage_mv / 1000.0
                calibrated_voltage = voltage_v + OFFSET_CALIBRATION
                
                readings.append({
                    'time': time.time() - start_time,
                    'voltage': calibrated_voltage,
                    'raw': raw_adc
                })
                
                sample_count += 1
                print(f"\r采样 {sample_count}: {calibrated_voltage:8.4f}V (耗时: {time.time() - start_time:.3f}s)", end='')
                
            except Exception as e:
                print(f"\n采样错误: {e}")
                continue
        
        bus.close()
        
        # 统计结果
        if readings:
            voltages = [r['voltage'] for r in readings]
            avg_v = sum(voltages) / len(voltages)
            min_v = min(voltages)
            max_v = max(voltages)
            duration = readings[-1]['time'] if readings else 0
            sampling_rate = len(readings) / duration if duration > 0 else 0
            
            print(f"\n\n📊 1秒钟测试结果:")
            print(f"   总采样数: {len(readings)} 次")
            print(f"   实际耗时: {duration:.3f} 秒")
            print(f"   采样率: {sampling_rate:.1f} SPS")
            print(f"   平均电压: {avg_v:.4f}V")
            print(f"   最小电压: {min_v:.4f}V")
            print(f"   最大电压: {max_v:.4f}V")
            print(f"   波动范围: {max_v - min_v:.4f}V")
            
            # 显示前几个和后几个采样点
            print(f"\n📈 采样数据预览:")
            preview_count = min(5, len(readings))
            for i in range(preview_count):
                r = readings[i]
                print(f"   [{i+1}] {r['time']:.3f}s: {r['voltage']:.4f}V")
            
            if len(readings) > preview_count:
                print("   ...")
                for i in range(-preview_count, 0):
                    r = readings[i]
                    print(f"   [{len(readings)+i+1}] {r['time']:.3f}s: {r['voltage']:.4f}V")
        
        return True
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断测试")
        return False
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        return False

def calibrate_zero_offset():
    """零点校准功能"""
    print("\n=== 零点校准 ===")
    print("请确保输入端接地(0V)，然后按回车键开始校准...")
    
    try:
        input()  # 等待用户确认
        
        # 进行零点测量
        print("开始零点测量...")
        zero_readings = []
        
        # 使用直接I2C方式进行校准测量
        bus = smbus2.SMBus(I2C_BUS)
        
        # 配置ADS1115
        config_value = 0x8583  # 与测试配置相同
        config_bytes = [(config_value >> 8) & 0xFF, config_value & 0xFF]
        bus.write_i2c_block_data(ADS1115_ADDR, 0x01, config_bytes)
        
        # 读取10个样本取平均
        for i in range(10):
            time.sleep(0.1)
            data = bus.read_i2c_block_data(ADS1115_ADDR, 0x00, 2)
            raw_adc = (data[0] << 8) | data[1]
            if raw_adc > 32767:
                raw_adc -= 65536
            voltage_mv = raw_adc * 0.125
            voltage_v = voltage_mv / 1000.0
            zero_readings.append(voltage_v)
            print(f"   样本 {i+1}: {voltage_v:8.4f}V")
        
        bus.close()
        
        # 计算零点偏移
        avg_zero = sum(zero_readings) / len(zero_readings)
        global OFFSET_CALIBRATION
        OFFSET_CALIBRATION = -avg_zero  # 取反作为校准值
        
        print(f"\n✅ 零点校准完成!")
        print(f"   平均零点读数: {avg_zero:.4f}V")
        print(f"   校准偏移值: {OFFSET_CALIBRATION:+.4f}V")
        print(f"   校准后预期读数: 0.0000V")
        
        return True
        
    except KeyboardInterrupt:
        print("\n❌ 用户取消校准")
        return False
    except Exception as e:
        print(f"\n❌ 校准失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 ADS1115简单测试程序")
    print(f"配置: 地址=0x{ADS1115_ADDR:02X}, 增益={TEST_GAIN}x, 通道=A{TEST_CHANNEL}")
    if abs(OFFSET_CALIBRATION) > 0.001:
        print(f"⚙️  当前偏移校准: {OFFSET_CALIBRATION:+.4f}V")
    print("=" * 50)
    
    # 询问是否需要校准
    print("\n是否需要进行零点校准? (y/N): ")
    try:
        choice = input().strip().lower()
        if choice == 'y' or choice == 'yes':
            if not calibrate_zero_offset():
                return
    except:
        pass  # 继续执行测试
    
    # 询问是否进行1秒钟连续测试
    print("\n是否进行1秒钟连续测试? (y/N): ")
    try:
        choice = input().strip().lower()
        if choice == 'y' or choice == 'yes':
            continuous_test_1s()
            return
    except:
        pass  # 继续执行常规测试
    
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