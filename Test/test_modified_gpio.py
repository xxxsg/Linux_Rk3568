#!/usr/bin/env python3
"""
测试修改后的GPIO控制器
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from app import GPIOController
import time

def test_gpio_controller():
    """测试GPIO控制器的基本功能"""
    print("=== 测试修改后的GPIO控制器 ===")
    
    # 创建控制器实例
    controller = GPIOController("gpiochip1", 0, 1)
    
    try:
        print(f"模拟模式: {controller.sim_mode}")
        
        if not controller.sim_mode:
            print("硬件模式测试:")
            # 测试LED1
            print("测试LED1...")
            controller.set_led1(1)
            print(f"LED1状态: {controller.get_led1()}")
            time.sleep(1)
            
            controller.set_led1(0)
            print(f"LED1状态: {controller.get_led1()}")
            time.sleep(1)
            
            # 测试LED2
            print("测试LED2...")
            controller.set_led2(1)
            print(f"LED2状态: {controller.get_led2()}")
            time.sleep(1)
            
            controller.set_led2(0)
            print(f"LED2状态: {controller.get_led2()}")
            
            # 测试切换功能
            print("测试切换功能...")
            controller.toggle_led1()
            print(f"LED1切换后状态: {controller.get_led1()}")
            controller.toggle_led1()
            print(f"LED1再次切换后状态: {controller.get_led1()}")
            
        else:
            print("模拟模式测试:")
            controller.set_led1(1)
            print(f"LED1状态: {controller.get_led1()}")
            controller.set_led2(1)
            print(f"LED2状态: {controller.get_led2()}")
            
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
    finally:
        # 清理资源
        controller.cleanup()
        print("测试完成，资源已清理")

if __name__ == "__main__":
    test_gpio_controller()