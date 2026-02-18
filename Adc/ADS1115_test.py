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
import gpiod

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置参数
I2C_BUS = 1
ADS1115_ADDR = 0x48  # 使用i2cteset.py中的地址
TEST_GAIN = 8        # 8倍增益
TEST_CHANNEL = 0     # 单通道测试

# DRDY中断配置
DRDY_CHIP_NAME = 'gpiochip1'  # DRDY使用的GPIO芯片
DRDY_LINE_NUMBER = 1           # DRDY连接的线路号

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







def single_channel_drdy_test():
    """单通道DRDY中断测试功能"""
    current_range = GAIN_SETTINGS[CURRENT_GAIN]['range']
    print(f"\n=== 单通道DRDY中断测试 (量程: {current_range}) ===")
    print(f"测试通道: AIN{TEST_CHANNEL}")
    print(f"GPIO芯片: {DRDY_CHIP_NAME}, 线路: {DRDY_LINE_NUMBER}")
    print("按 Ctrl+C 停止测试")
    print()
    
    # 显示表头
    print("触发次数   时间(s)    电压(mV)   状态")
    print("--------   -------    --------   ----")
    
    try:
        # 初始化GPIO (gpiod 1.x 写法)
        chip = gpiod.Chip(DRDY_CHIP_NAME)
        drdy_line = chip.get_line(DRDY_LINE_NUMBER)
        
        # 配置为上升沿中断
        drdy_line.request(
            consumer='adc-drdy-test',
            type=gpiod.LINE_REQ_EV_RISING_EDGE
        )
        
        print(f"✅ DRDY中断已配置 - {DRDY_CHIP_NAME} line {DRDY_LINE_NUMBER}")
        
        # 初始化I2C
        bus = smbus2.SMBus(I2C_BUS)
        start_time = time.time()
        trigger_count = 0
        
        while True:
            # 等待DRDY中断事件
            if drdy_line.event_wait(sec=1):  # 1秒超时
                event = drdy_line.event_read()
                if event.type == gpiod.LineEvent.RISING_EDGE:
                    trigger_count += 1
                    elapsed_time = time.time() - start_time
                    
                    # 读取单通道数据
                    voltage_mv = read_channel_mv(bus, TEST_CHANNEL)
                    
                    # 格式化显示
                    if voltage_mv is not None:
                        voltage_str = f"{voltage_mv:8.2f}"
                        status = "✅ 正常"
                    else:
                        voltage_str = f"{'--':>8}"
                        status = "❌ 错误"
                    
                    # 一行输出数据
                    print(f"{trigger_count:8d}   {elapsed_time:7.2f}    {voltage_str}   {status}")
            
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户停止测试")
        drdy_line.release()
        chip.close()
        bus.close()
        return True
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        try:
            drdy_line.release()
            chip.close()
        except:
            pass
        bus.close()
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
    print("🚀 ADS1115单通道DRDY测试程序启动")
    
    # 直接执行单通道DRDY中断测试
    single_channel_drdy_test()

if __name__ == "__main__":
    main()