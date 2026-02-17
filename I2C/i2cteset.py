#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
I2C & GPIO 快速测试脚本 (gpiod 1.x 风格)
设备：TCA9555(0x20), PCF8574(0x21), ADS1115(0x48)
功能：设置 P2 为高电平，等待用户输入后退出
"""

import smbus2
import gpiod
import time

# ================= 配置区域 =================
I2C_BUS_NUM = 1
I2C_DEVICES = {
    0x20: "TCA9555",
    0x21: "PCF8574",
    0x48: "ADS1115"
}
# ===========================================

def test_i2c_devices():
    """测试 I2C 设备通信"""
    print("\n=== [1] I2C 设备测试 ===")
    bus = smbus2.SMBus(I2C_BUS_NUM)
    
    for addr, name in I2C_DEVICES.items():
        try:
            if name == "ADS1115":
                val = bus.read_word_data(addr, 0x00) 
                print(f"✅ {name} (0x{addr:02X}): ADC={val}")
                
            elif name == "TCA9555":
                val = bus.read_byte_data(addr, 0x00)
                print(f"✅ {name} (0x{addr:02X}): Input=0x{val:02X}")
                
            elif name == "PCF8574":
                val = bus.read_byte(addr)
                print(f"✅ {name} (0x{addr:02X}): State=0x{val:02X}")
                
        except Exception as e:
            print(f"❌ {name} (0x{addr:02X}): 失败 - {e}")
    
    bus.close()

def set_p2_high():
    """设置 TCA9555 和 PCF8574 的 P2 引脚为高电平"""
    print("\n=== [2] 设置 P2 为高电平 ===")
    bus = smbus2.SMBus(I2C_BUS_NUM)
    
    # --- TCA9555 P2 设置 ---
    print("\n【TCA9555】设置 P2 为高电平...")
    try:
        # 寄存器定义
        REG_CONFIG_PORT0 = 0x06  # 配置寄存器 (0=输出，1=输入)
        REG_OUTPUT_PORT0 = 0x02  # 输出寄存器
        
        # 读取当前配置
        config = bus.read_byte_data(0x20, REG_CONFIG_PORT0)
        print(f"  当前配置：0x{config:02X}")
        
        # 设置 P2 为输出 (对应 bit2，清零)
        config_new = config & ~(1 << 2)
        bus.write_byte_data(0x20, REG_CONFIG_PORT0, config_new)
        print(f"  新配置：0x{config_new:02X} (P2=输出)")
        
        # 读取当前输出
        output = bus.read_byte_data(0x20, REG_OUTPUT_PORT0)
        print(f"  当前输出：0x{output:02X}")
        
        # 设置 P2 为高电平 (对应 bit2，置 1)
        output_new = output | (1 << 2)
        bus.write_byte_data(0x20, REG_OUTPUT_PORT0, output_new)
        print(f"  新输出：0x{output_new:02X} (P2=高电平) ✅")
        
    except Exception as e:
        print(f"  ❌ TCA9555 设置失败：{e}")
    
    # --- PCF8574 P2 设置 ---
    print("\n【PCF8574】设置 P2 为高电平...")
    try:
        # 读取当前状态
        current = bus.read_byte(0x21)
        print(f"  当前状态：0x{current:02X}")
        
        # 设置 P2 为高电平 (对应 bit2，置 1)
        new_val = current | (1 << 2)
        bus.write_byte(0x21, new_val)
        print(f"  新状态：0x{new_val:02X} (P2=高电平) ✅")
        
    except Exception as e:
        print(f"  ❌ PCF8574 设置失败：{e}")
    
    bus.close()

def test_gpio_chips():
    """使用 gpiod 1.x 扫描 GPIO 芯片"""
    print("\n=== [3] GPIO 芯片扫描 (gpiod 1.x) ===")
    
    import os
    dev_path = "/dev/"
    
    for fname in os.listdir(dev_path):
        if fname.startswith("gpiochip"):
            chip_path = os.path.join(dev_path, fname)
            try:
                chip = gpiod.Chip(chip_path)
                name = chip.name()
                num_lines = chip.num_lines()
                print(f"✅ {name} ({fname}) - {num_lines} 线")
                chip.close()
            except:
                continue

def wait_for_user():
    """等待用户输入后退出"""
    print("\n" + "=" * 50)
    print("📌 P2 已设置为高电平")
    print("📌 按 Enter 键退出程序...")
    print("=" * 50)
    
    try:
        input()  # 等待用户按 Enter
    except KeyboardInterrupt:
        print("\n⚠️  用户中断 (Ctrl+C)")
    
    print("\n👋 程序退出，再见！")

def cleanup():
    """清理资源，将 P2 恢复为低电平"""
    print("\n=== [清理] 恢复 P2 为低电平 ===")
    bus = smbus2.SMBus(I2C_BUS_NUM)
    
    try:
        # TCA9555 P2 恢复低电平
        output = bus.read_byte_data(0x20, 0x02)
        output_new = output & ~(1 << 2)  # 清零 bit2
        bus.write_byte_data(0x20, 0x02, output_new)
        print("✅ TCA9555 P2 已恢复低电平")
        
        # PCF8574 P2 恢复低电平
        current = bus.read_byte(0x21)
        new_val = current & ~(1 << 2)  # 清零 bit2
        bus.write_byte(0x21, new_val)
        print("✅ PCF8574 P2 已恢复低电平")
        
    except Exception as e:
        print(f"⚠️ 清理失败：{e}")
    
    bus.close()

if __name__ == "__main__":
    print("🚀 开始 I2C & GPIO 测试...")
    
    try:
        # 1. 测试 I2C 通信
        test_i2c_devices()
        
        # 2. 设置 P2 为高电平
        set_p2_high()
        
        # 3. 扫描 GPIO 芯片
        test_gpio_chips()
        
        # 4. 等待用户输入
        wait_for_user()
        
    finally:
        # 5. 清理资源
        cleanup()