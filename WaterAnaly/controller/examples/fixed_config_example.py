#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PeriPump固定配置使用示例
演示固定配置：PUL(gpiod) + DIR/ENA(TCA9555)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fixed_configuration_example():
    """固定配置示例"""
    print("=== 固定配置示例 ===")
    
    try:
        from PeriPump import PeriPump
        from TCA9555 import TCA9555
        
        # 初始化TCA9555实例
        tca9555 = TCA9555()
        
        # 创建PeriPump实例（固定配置）
        pump = PeriPump(tca9555_instance=tca9555)
        
        # 设置电机参数
        pump.set_speed(250)  # 250 RPM
        pump.set_subdivision(800)  # 800细分
        
        # 显示状态
        status = pump.get_status()
        print(f"当前状态: {status}")
        
        print("\n=== 演示对外暴露的控制函数 ===")
        
        # 演示方向控制
        print("设置正转方向...")
        pump.set_direction(1)
        
        print("使能电机...")
        pump.enable_motor()
        
        print("发送10个脉冲...")
        for i in range(10):
            pump.send_single_pulse()
            time.sleep(0.001)  # 1ms间隔
        
        print("禁用电机（紧急停止）...")
        pump.disable_motor()
        
        print("\n=== 演示完整旋转功能 ===")
        # 正转2圈
        print("执行正转2圈...")
        pump.rotate(direction=1, revolutions=2.0)
        
        # 等待1秒
        time.sleep(1)
        
        # 反转1圈
        print("执行反转1圈...")
        pump.rotate(direction=0, revolutions=1.0)
        
        # 清理资源
        pump.cleanup()
        tca9555.cleanup()
        
        print("固定配置示例完成!")
        
    except Exception as e:
        print(f"固定配置示例出错: {e}")

def emergency_stop_example():
    """紧急停止示例"""
    print("=== 紧急停止示例 ===")
    
    try:
        from PeriPump import PeriPump
        from TCA9555 import TCA9555
        import time
        
        tca9555 = TCA9555()
        pump = PeriPump(tca9555_instance=tca9555)
        
        print("开始连续运行...")
        pump.set_direction(1)
        pump.enable_motor()
        
        # 模拟长时间运行
        print("运行中... (按Ctrl+C紧急停止)")
        try:
            pulse_count = 0
            start_time = time.time()
            while True:
                pump.send_single_pulse()
                pulse_count += 1
                if pulse_count % 1000 == 0:
                    elapsed = time.time() - start_time
                    print(f"已发送 {pulse_count} 个脉冲，运行 {elapsed:.1f} 秒")
                time.sleep(0.001)  # 1ms脉冲间隔
                
        except KeyboardInterrupt:
            print("\n检测到中断信号，执行紧急停止...")
            pump.disable_motor()  # 使用暴露的紧急停止函数
            print("电机已紧急停止!")
        
        pump.cleanup()
        tca9555.cleanup()
        
    except Exception as e:
        print(f"紧急停止示例出错: {e}")

if __name__ == "__main__":
    print("PeriPump固定配置示例")
    print("1. 基本功能演示")
    print("2. 紧急停止演示")
    
    choice = input("请选择示例 (1-2): ")
    
    if choice == "1":
        fixed_configuration_example()
    elif choice == "2":
        emergency_stop_example()
    else:
        print("运行默认示例...")
        fixed_configuration_example()