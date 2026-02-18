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
TEST_GAIN = 8        # 8倍增益
TEST_CHANNELS = [0, 1, 2, 3]  # 测试所有4个通道
TEST_SAMPLES = 5     # 测试样本数
TEST_DURATION = 1.0  # 测试持续时间(秒)

# 增益配置和量程信息 (根据ADS1115寄存器定义)
GAIN_SETTINGS = {
    0.667: {'coeff': 0.1875, 'range': '±6.144V', 'pga': 0x00, 'desc': '2/3倍增益'},
    1: {'coeff': 0.125, 'range': '±4.096V', 'pga': 0x02, 'desc': '1倍增益'},
    2: {'coeff': 0.0625, 'range': '±2.048V', 'pga': 0x04, 'desc': '2倍增益'},
    4: {'coeff': 0.03125, 'range': '±1.024V', 'pga': 0x06, 'desc': '4倍增益'},
    8: {'coeff': 0.015625, 'range': '±512mV', 'pga': 0x08, 'desc': '8倍增益'},
    16: {'coeff': 0.0078125, 'range': '±256mV', 'pga': 0x0A, 'desc': '16倍增益'}
}

# 当前配置
CURRENT_GAIN = 8
VOLTAGE_COEFFICIENT_MV = GAIN_SETTINGS[CURRENT_GAIN]['coeff']
CURRENT_PGA = GAIN_SETTINGS[CURRENT_GAIN]['pga']

# 通道配置映射
CHANNEL_CONFIGS = {
    0: 0x40,  # AIN0 vs GND
    1: 0x50,  # AIN1 vs GND  
    2: 0x60,  # AIN2 vs GND
    3: 0x70   # AIN3 vs GND
}

def read_channel_mv(bus, channel):
    """读取指定通道的电压值(mV)"""
    try:
        # 配置通道
        if channel in CHANNEL_CONFIGS:
            mux_config = CHANNEL_CONFIGS[channel]
        else:
            mux_config = 0x40  # 默认AIN0
        
        # 配置寄存器: 当前增益, 指定通道, 单次转换
        config_value = 0x8000 | mux_config | CURRENT_PGA | 0x01  # OS=1, MUX, PGA, MODE=1
        config_bytes = [(config_value >> 8) & 0xFF, config_value & 0xFF]
        bus.write_i2c_block_data(ADS1115_ADDR, 0x01, config_bytes)
        
        # 等待转换完成
        time.sleep(0.1)
        
        # 读取数据
        data = bus.read_i2c_block_data(ADS1115_ADDR, 0x00, 2)
        raw_adc = (data[0] << 8) | data[1]
        
        # 处理符号位
        if raw_adc > 32767:
            raw_adc -= 65536
        
        # 转换为毫伏
        voltage_mv = raw_adc * VOLTAGE_COEFFICIENT_MV
        return voltage_mv
        
    except Exception as e:
        print(f"通道 {channel} 读取失败: {e}")
        return None

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
                voltage_mv = result['r'] * (0.015625 / 0.125)  # 调整DFRobot库的系数
                voltages.append(voltage_mv)
                
                print(f"   读数 {i+1}: {voltage_mv:8.2f}mV")
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   读数 {i+1}: 失败 - {e}")
        
        # 统计结果
        if voltages:
            avg_mv = sum(voltages) / len(voltages)
            print(f"\n📊 平均电压: {avg_mv:.2f}mV")
            
        return True
        
    except Exception as e:
        print(f"❌ DFRobot测试失败: {e}")
        return False

def test_with_direct_i2c():
    """直接使用I2C进行测试"""
    current_range = GAIN_SETTINGS[CURRENT_GAIN]['range']
    print(f"\n=== 直接I2C访问测试 (量程: {current_range}) ===")
    
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
        print("2. 配置当前增益...")
        try:
            # 配置寄存器: 当前增益, A0输入, 单次转换
            config_value = 0x8000 | 0x40 | CURRENT_PGA | 0x01  # OS=1, MUX=100, PGA, MODE=1
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
                
                # 转换为毫伏 (8倍增益: 0.015625mV/bit)
                voltage_mv = raw_adc * VOLTAGE_COEFFICIENT_MV
                voltages.append(voltage_mv)
                
                print(f"   读数 {i+1}: {voltage_mv:8.2f}mV (原始值: {raw_adc})")
                
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
            
            # 根据增益动态评估范围
            current_range_mv = float(GAIN_SETTINGS[CURRENT_GAIN]['range'].replace('±', '').replace('mV', '').replace('V', ''))
            if 'V' in GAIN_SETTINGS[CURRENT_GAIN]['range']:
                current_range_mv *= 1000  # 转换为mV
            
            threshold_low = current_range_mv * 0.02  # 2%量程
            threshold_high = current_range_mv * 0.8   # 80%量程
            
            if abs(avg_v) < threshold_low:
                print(f"   📊 评估: 接近0mV (可能未连接信号)")
            elif threshold_low <= abs(avg_v) <= threshold_high:
                print(f"   📊 评估: 正常范围 (信号连接正常)")
            else:
                print(f"   📊 评估: 接近满量程 (建议降低增益或检查信号)")
        
        return True
        
    except Exception as e:
        print(f"❌ 直接I2C测试失败: {e}")
        return False

def multi_channel_test():
    """多通道同时测试功能"""
    current_range = GAIN_SETTINGS[CURRENT_GAIN]['range']
    print(f"\n=== 4通道同时测试 (量程: {current_range}) ===")
    
    try:
        bus = smbus2.SMBus(I2C_BUS)
        
        # 一行显示4个通道
        print("AIN0(mV)   AIN1(mV)   AIN2(mV)   AIN3(mV)   状态")
        print("--------   --------   --------   --------   ----")
        
        channel_results = {}
        channel_voltages = []
        
        # 依次读取4个通道
        for channel in TEST_CHANNELS:
            voltage_mv = read_channel_mv(bus, channel)
            if voltage_mv is not None:
                channel_results[channel] = voltage_mv
                channel_voltages.append(voltage_mv)
            else:
                channel_results[channel] = None
                channel_voltages.append(None)
            time.sleep(0.05)  # 短暂延时
        
        # 一行输出所有通道数据
        voltage_strs = []
        for voltage in channel_voltages:
            if voltage is not None:
                voltage_strs.append(f"{voltage:8.2f}")
            else:
                voltage_strs.append(f"{'--':>8}")
        
        # 检查所有通道状态
        all_valid = all(v is not None for v in channel_voltages)
        status = "✅ 全部正常" if all_valid else "⚠️  部分错误"
        
        print(f"{voltage_strs[0]}   {voltage_strs[1]}   {voltage_strs[2]}   {voltage_strs[3]}   {status}")
        
        bus.close()
        
        # 统计有效通道
        valid_voltages = [v for v in channel_results.values() if v is not None]
        if valid_voltages:
            avg_mv = sum(valid_voltages) / len(valid_voltages)
            min_mv = min(valid_voltages)
            max_mv = max(valid_voltages)
            
            print(f"\n📊 统计结果:")
            print(f"   有效通道: {len(valid_voltages)}/4")
            print(f"   平均值: {avg_mv:.2f}mV")
            print(f"   最小值: {min_mv:.2f}mV")
            print(f"   最大值: {max_mv:.2f}mV")
            print(f"   波动范围: {max_mv - min_mv:.2f}mV")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 多通道测试失败: {e}")
        return False

def continuous_multi_channel_test():
    """连续多通道测试功能 - 每秒循环测试并输出四通道数据"""
    current_range = GAIN_SETTINGS[CURRENT_GAIN]['range']
    print(f"\n=== 连续多通道测试 (量程: {current_range}) ===")
    print("按 Ctrl+C 停止测试")
    print()
    
    # 显示表头
    print("时间(s)    AIN0(mV)   AIN1(mV)   AIN2(mV)   AIN3(mV)   状态")
    print("-------    --------   --------   --------   --------   ----")
    
    try:
        bus = smbus2.SMBus(I2C_BUS)
        start_time = time.time()
        cycle_count = 0
        
        while True:
            cycle_start = time.time()
            cycle_count += 1
            
            # 读取四个通道
            channel_voltages = []
            all_valid = True
            
            for channel in TEST_CHANNELS:
                voltage_mv = read_channel_mv(bus, channel)
                if voltage_mv is not None:
                    channel_voltages.append(voltage_mv)
                else:
                    channel_voltages.append(None)
                    all_valid = False
                time.sleep(0.01)  # 短暂延时
            
            # 格式化电压显示
            voltage_strs = []
            for voltage in channel_voltages:
                if voltage is not None:
                    voltage_strs.append(f"{voltage:8.2f}")
                else:
                    voltage_strs.append(f"{'--':>8}")
            
            # 状态显示
            status = "✅ 正常" if all_valid else "⚠️  错误"
            elapsed_time = time.time() - start_time
            
            # 一行输出所有数据
            print(f"{elapsed_time:7.2f}    {voltage_strs[0]}   {voltage_strs[1]}   {voltage_strs[2]}   {voltage_strs[3]}   {status}")
            
            # 控制采样间隔约为1秒
            cycle_duration = time.time() - cycle_start
            if cycle_duration < 1.0:
                time.sleep(1.0 - cycle_duration)
                
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户停止测试")
        bus.close()
        return True
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        bus.close()
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
        config_value = 0x8000 | 0x40 | CURRENT_PGA | 0x01  # 与测试配置相同
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

def print_safety_notice():
    """打印安全注意事项和量程信息"""
    print("⚠️  ADS1115测试程序 - 安全注意事项")
    print("=" * 50)
    print("重要提醒：")
    print("1. 确保待测信号与ADS1115共地")
    print("2. 输入电压不得超过当前量程")
    print("3. 测试前请确认接线正确")
    print()
    
    print("📋 当前配置量程表：")
    print("增益    量程       分辨率     PGA值   适用场景")
    print("------  ----------  ---------  ------  --------")
    for gain, info in sorted(GAIN_SETTINGS.items()):
        marker = "★" if gain == CURRENT_GAIN else "○"
        gain_display = f"{gain:.3f}" if gain < 1 else f"{int(gain)}"
        print(f"{marker} {gain_display:>5}x  {info['range']:>10}  {info['coeff']:.5f}mV/bit  0x{info['pga']:02X}    {info['desc']}")
    print()
    print(f"当前设置: {GAIN_SETTINGS[CURRENT_GAIN]['desc']} ({GAIN_SETTINGS[CURRENT_GAIN]['range']})")
    print("=" * 50)

def main():
    """主函数"""
    print_safety_notice()
    print()
    print("🚀 ADS1115连续多通道测试程序启动")
    
    # 直接执行连续多通道测试
    continuous_multi_channel_test()
    
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