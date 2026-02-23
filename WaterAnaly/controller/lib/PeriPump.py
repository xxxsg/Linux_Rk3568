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
# 1. 默认run方法：使用 REVOLUTIONS(圈数) + RPM(转速) 控制
# 2. by_time_run方法：使用 SECEND(秒数) + RPM(转速) 控制
# 调用时可根据实际需求选择合适的运行方式和参数




class PeriPump:
    def __init__(self, tca9555_instance, pul_chip=None, pul_line=None, dir_pin=None, ena_pin=None):
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
        self.pul_chip = pul_chip if pul_chip is not None else PUL_CHIP
        self.pul_line = pul_line if pul_line is not None else PUL_LINE
        self.dir_pin = dir_pin if dir_pin is not None else DIR_PIN
        self.ena_pin = ena_pin if ena_pin is not None else ENA_PIN
        
        # 固定配置
        self.tca9555 = tca9555_instance
        self._setup_gpiod()
        
        # 电机参数 - 可在运行时修改
        self.subdivision = SUBDIVISION  # 电机细分，影响步进精度
        self.rpm = RPM                  # 当前转速(转/分钟)
        self.direction = DIRECTION      # 当前运行方向
        
        print("PeriPump初始化完成")
    
    # 对外接口函数
    def set_direction(self, direction):
        '''设置运行方向
        
        Args:
            direction (int): 1=正转, 0=反转
        '''
        if direction == 1:
            self.tca9555.set_tca9555_pin_high(self.dir_pin)
        else:
            self.tca9555.set_tca9555_pin_low(self.dir_pin)
        self.direction = direction
        print(f"方向设置: {'正转' if direction == 1 else '反转'}")
    
    def enable(self):
        '''使能电机'''
        self.tca9555.set_tca9555_pin_low(self.ena_pin)
        print("电机已使能")
    
    def disable(self):
        '''禁用电机（紧急停止）'''
        self.tca9555.set_tca9555_pin_high(self.ena_pin)
        print("电机已禁用")
    
    def pulse(self):
        '''发送单个脉冲'''
        self.line_pul.set_value(1)
        time.sleep(0.000125)  # 800Hz对应的半周期
        self.line_pul.set_value(0)
        time.sleep(0.000125)
    
    def run(self, revolutions=None, rpm=None, direction=None):
        '''按圈数运行 - 默认运行方法
        
        Args:
            revolutions (int, optional): 运行圈数，默认使用REVOLUTIONS
            rpm (int, optional): 转速(转/分钟)，默认使用当前rpm值
            direction (int, optional): 运行方向(1=正转,0=反转)，默认使用当前direction值
        '''
        # 使用传入参数或默认值
        revs = revolutions if revolutions is not None else REVOLUTIONS
        current_rpm = rpm if rpm is not None else self.rpm
        current_direction = direction if direction is not None else self.direction
        
        print(f"开始运行 {revs} 圈，转速 {current_rpm} RPM")
        self.set_direction(current_direction)
        self.enable()
        
        try:
            # 计算总脉冲数：圈数 × 细分
            total_pulses = int(revs * self.subdivision)
            # 计算脉冲间隔时间(秒)
            pulse_interval = 60.0 / (current_rpm * self.subdivision)
            
            print(f"总计脉冲数: {total_pulses}, 脉冲间隔: {pulse_interval*1000:.2f}ms")
            
            for i in range(total_pulses):
                self.pulse()
                time.sleep(pulse_interval)
                
        except KeyboardInterrupt:
            print("用户中断")
        finally:
            self.disable()
    
    def run_by_time(self, seconds=None, rpm=None, direction=None):
        '''按时间运行
        
        Args:
            seconds (float, optional): 运行时间(秒)，默认使用SECEND
            rpm (int, optional): 转速(转/分钟)，默认使用当前rpm值
            direction (int, optional): 运行方向(1=正转,0=反转)，默认使用当前direction值
        '''
        # 使用传入参数或默认值
        run_time = seconds if seconds is not None else SECEND
        current_rpm = rpm if rpm is not None else self.rpm
        current_direction = direction if direction is not None else self.direction
        
        print(f"开始运行 {run_time} 秒，转速 {current_rpm} RPM")
        self.set_direction(current_direction)
        self.enable()
        
        try:
            start_time = time.time()
            # 计算脉冲间隔时间(秒)
            pulse_interval = 60.0 / (current_rpm * self.subdivision)
            
            while (time.time() - start_time) < run_time:
                self.pulse()
                time.sleep(pulse_interval)
                
        except KeyboardInterrupt:
            print("用户中断")
        finally:
            self.disable()
    
    def set_pin_config(self, pul_chip=None, pul_line=None, dir_pin=None, ena_pin=None):
        '''设置引脚配置并重新初始化gpiod
        
        Args:
            pul_chip (str, optional): 脉冲信号GPIO芯片路径
            pul_line (int, optional): 脉冲信号引脚线号
            dir_pin (int, optional): 方向控制引脚号
            ena_pin (int, optional): 使能控制引脚号
        
        Note:
            修改引脚配置后会自动重新初始化gpiod
        '''
        if pul_chip is not None:
            self.pul_chip = pul_chip
        if pul_line is not None:
            self.pul_line = pul_line
        if dir_pin is not None:
            self.dir_pin = dir_pin
        if ena_pin is not None:
            self.ena_pin = ena_pin
        
        # 重新配置gpiod引脚
        self._setup_gpiod()
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
    
    # 内部函数
    def _setup_gpiod(self):
        '''配置gpiod引脚'''
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
        print(f"PUL引脚配置完成: {self.pul_chip}, 线号: {self.pul_line}")