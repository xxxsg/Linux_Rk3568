#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PeriPump混合IO模式使用示例
演示如何为不同引脚配置不同的IO模式
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def mixed_io_example():
    """混合IO模式示例：PUL使用gpiod，DIR和ENA使用TCA9555"""
    print("=== 混合IO模式示例 ===")
    
    try:
        from PeriPump import PeriPump
        from TCA9555 import TCA9555
        
        # 初始化TCA9555实例
        tca9555 = TCA9555()
        
        # 创建PeriPump实例（不预先配置引脚）
        pump = PeriPump()
        
        # 分别配置每个引脚
        print("配置PUL引脚为gpiod模式...")
        pump.configure_pin(
            pin_name='pul',
            mode='gpiod',
            chip_name='gpiochip1',
            line_number=1
        )
        
        print("配置DIR引脚为TCA9555模式...")
        pump.configure_pin(
            pin_name='dir',
            mode='tca9555',
            tca9555_instance=tca9555,
            pin_number=11  # 使用P11
        )
        
        print("配置ENA引脚为TCA9555模式...")
        pump.configure_pin(
            pin_name='ena',
            mode='tca9555',
            tca9555_instance=tca9555,
            pin_number=12  # 使用P12
        )
        
        # 设置电机参数
        pump.set_speed(250)  # 250 RPM
        pump.set_subdivision(800)  # 800细分
        
        # 显示状态
        status = pump.get_status()
        print(f"当前状态: {status}")
        
        # 正转2圈
        print("\n执行正转2圈...")
        pump.rotate(direction=1, revolutions=2.0)
        
        # 等待1秒
        import time
        time.sleep(1)
        
        # 反转1圈
        print("\n执行反转1圈...")
        pump.rotate(direction=0, revolutions=1.0)
        
        # 清理资源
        pump.cleanup()
        tca9555.cleanup()
        
        print("混合IO模式示例完成!")
        
    except Exception as e:
        print(f"混合IO模式示例出错: {e}")

def initialization_example():
    """初始化时配置引脚的示例"""
    print("=== 初始化配置示例 ===")
    
    try:
        from PeriPump import PeriPump
        from TCA9555 import TCA9555
        
        # 初始化TCA9555实例
        tca9555 = TCA9555()
        
        # 在初始化时配置所有引脚
        pump = PeriPump(
            pul_config={
                'mode': 'gpiod',
                'chip_name': 'gpiochip1',
                'line_number': 1
            },
            dir_config={
                'mode': 'tca9555',
                'tca9555_instance': tca9555,
                'pin_number': 11
            },
            ena_config={
                'mode': 'tca9555',
                'tca9555_instance': tca9555,
                'pin_number': 12
            }
        )
        
        # 设置参数并运行
        pump.set_speed(200)
        pump.run_for_time(direction=1, duration_seconds=3.0)
        
        pump.cleanup()
        tca9555.cleanup()
        
        print("初始化配置示例完成!")
        
    except Exception as e:
        print(f"初始化配置示例出错: {e}")

if __name__ == "__main__":
    print("PeriPump混合IO模式示例")
    print("1. 分步配置示例（推荐）")
    print("2. 初始化配置示例")
    
    choice = input("请选择示例 (1-2): ")
    
    if choice == "1":
        mixed_io_example()
    elif choice == "2":
        initialization_example()
    else:
        print("运行默认示例...")
        mixed_io_example()