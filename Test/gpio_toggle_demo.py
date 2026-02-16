#!/usr/bin/env python3
"""
GPIO切换演示
这个脚本演示了如何获取GPIO引脚的状态并进行切换，使用/sys/class/gpio接口
"""

import os
import time
import sys


def export_gpio(gpio_num):
    """
    导出GPIO到用户空间
    :param gpio_num: GPIO编号
    """
    gpio_export_path = "/sys/class/gpio/export"
    gpio_dir_path = f"/sys/class/gpio/gpio{gpio_num}"
    
    # 检查GPIO是否已经导出
    if os.path.exists(gpio_dir_path):
        return True
    
    try:
        with open(gpio_export_path, 'w') as f:
            f.write(str(gpio_num))
        # 等待GPIO导出完成
        time.sleep(0.1)
        return True
    except PermissionError:
        print(f"错误: 没有权限导出GPIO {gpio_num}。请尝试使用sudo运行。")
        return False
    except Exception as e:
        print(f"导出GPIO {gpio_num} 时出错: {e}")
        return False


def set_gpio_direction(gpio_num, direction):
    """
    设置GPIO的方向（输入/输出）
    :param gpio_num: GPIO编号
    :param direction: 方向 ("in" 或 "out")
    :return: 是否成功
    """
    gpio_direction_path = f"/sys/class/gpio/gpio{gpio_num}/direction"
    
    if not os.path.exists(gpio_direction_path):
        print(f"GPIO {gpio_num} 未导出或不存在")
        return False
    
    try:
        with open(gpio_direction_path, 'w') as f:
            f.write(direction)
        return True
    except PermissionError:
        print(f"错误: 没有权限设置GPIO {gpio_num} 方向。请尝试使用sudo运行。")
        return False
    except Exception as e:
        print(f"设置GPIO {gpio_num} 方向时出错: {e}")
        return False


def get_gpio_value(gpio_num):
    """
    获取GPIO的值
    :param gpio_num: GPIO编号
    :return: GPIO的值 (0 或 1)，失败返回None
    """
    gpio_value_path = f"/sys/class/gpio/gpio{gpio_num}/value"
    
    if not os.path.exists(gpio_value_path):
        print(f"GPIO {gpio_num} 未导出或不存在")
        return None
    
    try:
        with open(gpio_value_path, 'r') as f:
            value = f.read().strip()
        return int(value)
    except Exception as e:
        print(f"读取GPIO {gpio_num} 值时出错: {e}")
        return None


def set_gpio_value(gpio_num, value):
    """
    设置GPIO的值
    :param gpio_num: GPIO编号
    :param value: 要设置的值 (0 或 1)
    :return: 是否成功
    """
    gpio_value_path = f"/sys/class/gpio/gpio{gpio_num}/value"
    
    if not os.path.exists(gpio_value_path):
        print(f"GPIO {gpio_num} 未导出或不存在")
        return False
    
    try:
        with open(gpio_value_path, 'w') as f:
            f.write(str(value))
        return True
    except Exception as e:
        print(f"设置GPIO {gpio_num} 值时出错: {e}")
        return False


def get_gpio_status(gpio_num):
    """
    获取指定GPIO的状态
    :param gpio_num: GPIO编号
    :return: True表示高电平(HIGH)，False表示低电平(LOW)，失败返回None
    """
    # 先导出GPIO
    if not export_gpio(gpio_num):
        return None
    
    # 设置为输入模式
    if not set_gpio_direction(gpio_num, "in"):
        return None
    
    # 读取值
    value = get_gpio_value(gpio_num)
    if value is None:
        return None
    
    return value == 1


def toggle_gpio(gpio_num):
    """
    切换指定GPIO的状态 - 如果是HIGH就改为LOW，如果是LOW就改为HIGH
    :param gpio_num: GPIO编号
    :return: 新状态(True/False) 或 None(如果失败)
    """
    # 先导出GPIO
    if not export_gpio(gpio_num):
        return None
    
    # 设置为输出模式
    if not set_gpio_direction(gpio_num, "out"):
        return None
    
    # 获取当前状态
    current_status = get_gpio_value(gpio_num)
    if current_status is None:
        print("无法读取GPIO当前状态")
        return None
    
    # 确定新状态 - 如果当前是HIGH(1)，则设置为LOW(0)；如果当前是LOW(0)，则设置为HIGH(1)
    new_state = 1 - current_status
    
    print(f"GPIO {gpio_num} 当前状态: {'HIGH' if current_status else 'LOW'}, 将切换到: {'HIGH' if new_state else 'LOW'}")
    
    # 设置新状态
    if set_gpio_value(gpio_num, new_state):
        print(f"GPIO {gpio_num} 状态已成功切换到: {'HIGH' if new_state else 'LOW'}")
        return new_state == 1
    else:
        print(f"设置GPIO {gpio_num} 新状态时失败")
        return None


def switch_gpio_to_opposite(gpio_num):
    """
    获取GPIO当前状态，并切换到相反状态 - 如果是HIGH就改为LOW，如果是LOW就改为HIGH
    :param gpio_num: GPIO编号
    :return: 最终状态(True/False) 或 None(如果失败)
    """
    print(f"\n--- 切换GPIO {gpio_num} 状态 ---")
    
    # 获取当前状态
    current_status = get_gpio_status(gpio_num)
    if current_status is None:
        print(f"无法获取GPIO {gpio_num} 的当前状态")
        return None
    
    print(f"GPIO {gpio_num} 当前状态: {'HIGH' if current_status else 'LOW'}")
    
    # 切换到相反状态
    return toggle_gpio(gpio_num)


def find_gpio_by_chip_line(chip_idx, line_offset):
    """
    通过chip索引和line偏移量查找对应的GPIO编号
    :param chip_idx: chip索引
    :param line_offset: line偏移量
    :return: GPIO编号或None
    """
    # 查找gpiochip对应的基地址
    try:
        base_file = f"/sys/class/gpio/gpiochip{chip_idx}/base"
        if os.path.exists(base_file):
            with open(base_file, 'r') as f:
                base = int(f.read().strip())
            return base + line_offset
    except:
        pass
    
    # 如果无法找到确切的映射，尝试简单的估算（不准确但可以作为后备）
    # 每个chip通常管理32个GPIO，所以chip1 line1大约是GPIO 32+1=33
    return chip_idx * 32 + line_offset


def main():
    """主函数"""
    print("GPIO切换演示")
    print("================")
    
    # 根据用户需求：获取GPIO 33 (或 chip1 line1) 的状态并切换
    # 根据GPIO开发指南，我们需要正确计算GPIO编号
    
    print("\n方法 1: 使用chip1 line1 (估计GPIO编号)")
    chip_idx = 1
    line_offset = 1
    estimated_gpio = find_gpio_by_chip_line(chip_idx, line_offset)
    print(f"估计GPIO编号为: {estimated_gpio}")
    
    # 切换到相反状态
    new_status = switch_gpio_to_opposite(estimated_gpio)
    if new_status is not None:
        print(f"最终状态: {'HIGH' if new_status else 'LOW'}")
    else:
        print(f"无法切换GPIO {estimated_gpio} 的状态")
    
    print("\n方法 2: 直接使用GPIO 33")
    target_gpio = 33
    
    # 切换到相反状态
    new_status = switch_gpio_to_opposite(target_gpio)
    if new_status is not None:
        print(f"最终状态: {'HIGH' if new_status else 'LOW'}")
    else:
        print(f"无法切换GPIO {target_gpio} 的状态")
    
    print("\n注意:")
    print("- 此脚本使用/sys/class/gpio接口，这是Linux系统中标准的GPIO访问方式")
    print("- 如果GPIO不存在或没有权限访问，操作将会失败")
    print("- 如果GPIO正在被其他进程使用，可能也无法访问")
    print("- 请使用sudo运行此脚本以确保有足够的权限")


if __name__ == "__main__":
    main()