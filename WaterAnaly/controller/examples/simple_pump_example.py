#!/usr/bin/env python3
"""
简化版PeriPump使用示例
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def simple_example():
    """简单使用示例"""
    print("=== 简化版PeriPump示例 ===")
    
    try:
        from PeriPump import PeriPump
        from TCA9555 import TCA9555
        
        # 初始化
        tca9555 = TCA9555()
        pump = PeriPump(tca9555)
        
        # 基本操作
        print("\n1. 基本控制演示:")
        pump.set_direction(1)  # 正转
        pump.enable()          # 使能
        pump.pulse()           # 发送一个脉冲
        pump.disable()         # 禁用
        
        print("\n2. 连续运行演示:")
        pump.run(direction=1, seconds=3.0)  # 正转运行3秒
        
        print("\n3. 紧急停止演示:")
        pump.set_direction(0)  # 反转
        pump.enable()
        print("运行中... (按Ctrl+C停止)")
        try:
            while True:
                pump.pulse()
                time.sleep(0.001)
        except KeyboardInterrupt:
            pump.disable()  # 紧急停止
            print("已紧急停止")
        
        # 清理
        pump.cleanup()
        tca9555.cleanup()
        
        print("示例完成!")
        
    except Exception as e:
        print(f"示例出错: {e}")

if __name__ == "__main__":
    simple_example()