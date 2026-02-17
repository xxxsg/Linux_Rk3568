#!/usr/bin/env python3
# I2C 快速测试 - TCA9555(0x20)、PCF8574(0x21)、ADS1115(0x48)

import smbus2
import gpiod

I2C_BUS = 1
DEVICES = {0x20: "TCA9555", 0x21: "PCF8574", 0x48: "ADS1115"}

print("=== I2C 快速测试 ===\n")

# 1. 打开 I2C 总线
bus = smbus2.SMBus(I2C_BUS)
print(f"✅ I2C-{I2C_BUS} 总线已打开\n")

# 2. 扫描设备
print("【扫描设备】")
for addr, name in DEVICES.items():
    try:
        bus.read_byte(addr)
        print(f"  ✅ 0x{addr:02x} {name} 存在")
    except:
        print(f"  ❌ 0x{addr:02x} {name} 未找到")

# 3. 测试 TCA9555 (0x20)
print("\n【测试 TCA9555】")
try:
    data = bus.read_byte_data(0x20, 0x00)
    print(f"  读取输入端口：0x{data:02x}")
    bus.write_byte_data(0x20, 0x02, 0xFF)  # 输出高电平
    print(f"  设置输出高电平：0xFF ✅")
except Exception as e:
    print(f"  失败：{e}")

# 4. 测试 PCF8574 (0x21)
print("\n【测试 PCF8574】")
try:
    data = bus.read_byte(0x21)
    print(f"  读取 GPIO 状态：0x{data:02x}")
    bus.write_byte(0x21, 0xFF)  # 输出高电平
    print(f"  设置输出高电平：0xFF ✅")
except Exception as e:
    print(f"  失败：{e}")

# 5. 测试 ADS1115 (0x48)
print("\n【测试 ADS1115】")
try:
    config = bus.read_word_data(0x48, 0x01)
    print(f"  配置寄存器：0x{config:04x}")
    adc = bus.read_word_data(0x48, 0x00)
    print(f"  ADC 值：0x{adc:04x} ✅")
except Exception as e:
    print(f"  失败：{e}")

# 6. 查看 GPIO 芯片
print("\n【GPIO 芯片信息】")
try:
    # 遍历所有可能的GPIO芯片
    for i in range(10):  # 检查gpiochip0到gpiochip9
        try:
            chip_name = f"gpiochip{i}"
            chip = gpiod.Chip(f"/dev/{chip_name}")
            print(f"  {chip_name}: {chip.num_lines} 个 GPIO")
            chip.close()
        except:
            continue  # 芯片不存在时继续检查下一个
except Exception as e:
    print(f"  无法获取：{e}")

bus.close()
print("\n=== 测试完成 ===")