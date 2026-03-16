'''!
  @file PeriPump.py
  @brief 简化版蠕动泵控制类
'''

import time
import gpiod

# 电机参数
SUBDIVISION = 800  # 电机细分设置，影响步进精度，通常为400/800/1600等值

# 引脚定义 - 这些是硬件连接配置，初始化时需要设置
PUL_CHIP = '/dev/gpiochip1'  # 脉冲信号GPIO芯片路径
PUL_LINE = 1                 # 脉冲信号引脚线号
DIR_PIN = 11                 # 方向控制引脚号
ENA_PIN = 10                 # 使能控制引脚号

# 参数设置 - 这些是运行时可配置的参数
DIRECTION = 1      # 运行方向：1=正转，0=反转 (调用时可传入)
RPM = 300          # 转速(转/分钟) - 默认值 (调用时可传入)
REVOLUTIONS = 10   # 运行圈数 - 用于默认run方法 (调用时可传入)
SECEND = 3         # 运行时间(秒) - 用于by_time_run方法 (调用时可传入)

# 运行方法说明：
# 1. 默认run方法：使用 REVOLUTIONS(圈数) 控制
# 2. run_by_time方法：使用 SECEND(秒数) 控制
# 3. 通过 direction(), rpm(), subdivision() 方法设置运行参数
# 调用时可根据实际需求选择合适的运行方式和参数

from lib.TCA9555 import *


class PeriPump:
    def __init__(self, tca9555_instance:TCA9555, pul_chip=PUL_CHIP, pul_line=PUL_LINE, dir_pin=DIR_PIN, ena_pin=ENA_PIN):
        '''初始化蠕动泵控制器
        
        Args:
            tca9555_instance: TCA9555类的实例
            pul_chip (str, optional): 脉冲信号GPIO芯片路径，默认使用PUL_CHIP
            pul_line (int, optional): 脉冲信号引脚线号，默认使用PUL_LINE
            dir_pin (int, optional): 方向控制引脚号，默认使用DIR_PIN
            ena_pin (int, optional): 使能控制引脚号，默认使用ENA_PIN
        '''
        if tca9555_instance is None:
            raise ValueError("必须提供TCA9555实例")
        
        # 引脚配置 - 可在初始化时自定义
        self.pul_chip = pul_chip
        self.pul_line = pul_line
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin
        
        # 固定配置
        self.tca9555 = tca9555_instance
        self.set_pin_config()
        
        # 电机参数 - 可在运行时修改
        self._subdivision = SUBDIVISION  # 电机细分，影响步进精度
        self._rpm = RPM                  # 当前转速(转/分钟)
        self._direction = DIRECTION      # 当前运行方向
        
        print("PeriPump初始化完成")
    
    # 对外接口函数
    def enable(self):
        '''使能电机'''
        self.tca9555.write(self.ena_pin, False)
        print("电机已使能")
    
    def disable(self):
        '''禁用电机（紧急停止）'''
        self.tca9555.write(self.ena_pin, True)
        print("电机已禁用")
    
    def pulse(self):
        '''发送单个脉冲，根据当前转速和细分计算50%占空比的sleep时间'''
        # 计算脉冲间隔时间(秒) - 50%占空比
        pulse_interval = 30.0 / (self._rpm * self._subdivision)  # 60/2 = 30 (50%占空比)
        
        self.line_pul.set_value(1)
        time.sleep(pulse_interval)
        self.line_pul.set_value(0)
        time.sleep(pulse_interval)
    
    def run(self, revolutions=None):
        '''按圈数运行 - 默认运行方法
        
        Args:
            revolutions (int, optional): 运行圈数，默认使用REVOLUTIONS
        '''
        # 使用传入参数或默认值
        revs = revolutions if revolutions is not None else REVOLUTIONS
        
        print(f"开始运行 {revs} 圈，转速 {self._rpm} RPM")
        self.enable()
        
        try:
            # 计算总脉冲数：圈数 × 细分
            total_pulses = int(revs * self._subdivision)
            print(f"总计脉冲数: {total_pulses}")
            
            for i in range(total_pulses):
                self.pulse()
                
        except KeyboardInterrupt:
            print("用户中断")
        finally:
            self.disable()
    
    def run_by_time(self, seconds=None):
        '''按时间运行
        
        Args:
            seconds (float, optional): 运行时间(秒)，默认使用SECEND
        '''
        # 使用传入参数或默认值
        run_time = seconds if seconds is not None else SECEND
        
        print(f"开始运行 {run_time} 秒，转速 {self._rpm} RPM")
        self.enable()
        
        try:
            start_time = time.time()
            # 根据时间计算需要的脉冲数
            pulses_per_second = self._rpm * self._subdivision / 60.0
            total_pulses = int(run_time * pulses_per_second)
            
            print(f"总计脉冲数: {total_pulses}")
            
            for i in range(total_pulses):
                self.pulse()
                # 检查是否超时
                if (time.time() - start_time) >= run_time:
                    break
                
        except KeyboardInterrupt:
            print("用户中断")
        finally:
            self.disable()
    
    def set_pin_config(self, pul_chip=None, pul_line=None, dir_pin=None, ena_pin=None):
        '''设置引脚配置并初始化gpiod
        
        Args:
            pul_chip (str, optional): 脉冲信号GPIO芯片路径
            pul_line (int, optional): 脉冲信号引脚线号
            dir_pin (int, optional): 方向控制引脚号
            ena_pin (int, optional): 使能控制引脚号
        '''
        if pul_chip is not None: self.pul_chip = pul_chip
        if pul_line is not None: self.pul_line = pul_line
        if dir_pin is not None: self.dir_pin = dir_pin
        if ena_pin is not None: self.ena_pin = ena_pin
        
        # 清理旧的gpiod资源
        if hasattr(self, 'line_pul') and self.line_pul:
            try:
                self.line_pul.release()
            except:
                pass
        if hasattr(self, 'chip_pul') and self.chip_pul:
            try:
                self.chip_pul.close()
            except:
                pass
        
        # 配置新的gpiod引脚
        self.chip_pul = gpiod.Chip(self.pul_chip)
        self.line_pul = self.chip_pul.get_line(self.pul_line)
        self.line_pul.request(consumer="peri_pump", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        self.tca9555.set_mode([self.dir_pin, self.ena_pin], "output")
        print(f"引脚配置已更新: PUL({self.pul_chip}:{self.pul_line}), DIR({self.dir_pin}), ENA({self.ena_pin})")
    
    def cleanup(self):
        '''清理资源'''
        try:
            self.disable()
            self.line_pul.release()
            self.chip_pul.close()
            print("资源已清理")
        except:
            pass

    
    def subdivision(self, subdiv_value):
        '''设置电机细分
        Args:
            subdiv_value (int): 细分数
        '''
        self._subdivision = subdiv_value
        print(f"细分设置: {subdiv_value}")
    
    def direction(self, direction):
        '''设置运行方向
        Args:
            direction (int): 1=正转, 0=反转
        '''
        if direction == 1:
            self.tca9555.write(self.dir_pin, True)
        else:
            self.tca9555.write(self.dir_pin, False)
        self._direction = direction
        print(f"方向设置: {'正转' if direction == 1 else '反转'}")

    def rpm(self, rpm_value):
        '''设置转速
        Args:
            rpm_value (int): 转速(转/分钟)
        '''
        self._rpm = rpm_value
        print(f"转速设置: {rpm_value} RPM")    
    
    # 兼容性方法 - 保持原有接口可用
    def set_subdivision(self, subdiv_value):
        '''兼容性方法：设置细分'''
        return self.subdivision(subdiv_value)

    def set_direction(self, direction):
        '''兼容性方法：设置运行方向'''
        return self.direction(direction)
    
    def set_rpm(self, rpm_value):
        '''兼容性方法：设置转速'''
        return self.rpm(rpm_value)
    
