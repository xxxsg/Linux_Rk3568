"""测试Stepper类的基本功能"""

import sys
import os

# 添加lib目录到系统路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

# 直接导入Stepper类，避免导入lib包的其他模块
from stepper import Stepper


class MockPin:
    """模拟Pin类，用于测试"""
    def __init__(self, name):
        self.name = name
        self.value = False
    
    def write(self, value):
        self.value = value
        print(f"{self.name} set to {value}")
    
    def high(self):
        self.write(True)
    
    def low(self):
        self.write(False)
    
    def close(self):
        print(f"{self.name} closed")


# 测试Stepper类的基本功能
def test_stepper_basic():
    print("Testing Stepper class basic functionality...")
    
    # 创建模拟引脚
    pul_pin = MockPin("PUL")
    dir_pin = MockPin("DIR")
    
    # 创建Stepper实例
    stepper = Stepper(pul_pin=pul_pin, dir_pin=dir_pin, steps_per_rev=800)
    
    # 设置转速
    stepper.set_rpm(300)
    print(f"Stepper RPM set to: {stepper.rpm}")
    
    # 设置方向
    stepper.set_direction(True)
    print(f"Stepper direction set to forward: {stepper.forward}")
    
    # 测试脉冲输出
    print("Testing pulse_once...")
    stepper.pulse_once()
    
    # 测试停止功能
    print("Testing stop functionality...")
    stepper.stop()
    
    # 测试急停功能
    print("Testing emergency_stop functionality...")
    stepper.emergency_stop()
    
    # 测试清理功能
    print("Testing cleanup functionality...")
    stepper.cleanup()
    
    print("Stepper class basic functionality test completed successfully!")


if __name__ == "__main__":
    test_stepper_basic()
