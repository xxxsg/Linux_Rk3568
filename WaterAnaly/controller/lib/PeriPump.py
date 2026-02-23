'''!
  @file PeriPump.py
  @brief 简化版蠕动泵控制类
'''

import time

class PeriPump:
    def __init__(self, tca9555_instance):
        '''初始化蠕动泵控制器
        
        Args:
            tca9555_instance: TCA9555类的实例
        '''
        if tca9555_instance is None:
            raise ValueError("必须提供TCA9555实例")
        
        # 固定配置
        self.tca9555 = tca9555_instance
        self._setup_gpiod()
        
        # 电机参数
        self.subdivision = 800
        self.rpm = 300
        
        print("PeriPump初始化完成")
    
    # 对外接口函数
    def set_direction(self, direction):
        '''设置方向: 1=正转, 0=反转'''
        if direction == 1:
            self.tca9555.set_tca9555_pin_high(11)
        else:
            self.tca9555.set_tca9555_pin_low(11)
        print(f"方向设置: {'正转' if direction == 1 else '反转'}")
    
    def enable(self):
        '''使能电机'''
        self.tca9555.set_tca9555_pin_low(12)
        print("电机已使能")
    
    def disable(self):
        '''禁用电机（紧急停止）'''
        self.tca9555.set_tca9555_pin_high(12)
        print("电机已禁用")
    
    def pulse(self):
        '''发送单个脉冲'''
        self.line_pul.set_value(1)
        time.sleep(0.000125)  # 800Hz对应的半周期
        self.line_pul.set_value(0)
        time.sleep(0.000125)
    
    def run(self, direction=1, seconds=5.0):
        '''运行指定时间'''
        print(f"开始运行 {seconds} 秒")
        self.set_direction(direction)
        self.enable()
        
        try:
            start_time = time.time()
            while (time.time() - start_time) < seconds:
                self.pulse()
        except KeyboardInterrupt:
            print("用户中断")
        finally:
            self.disable()
    
    def cleanup(self):
        '''清理资源'''
        try:
            self.disable()
            self.line_pul.release()
            self.chip_pul.close()
            print("资源已清理")
        except:
            pass
    
    def _setup_gpiod(self):
        '''配置gpiod引脚'''
        import gpiod
        self.chip_pul = gpiod.Chip("/dev/gpiochip1")
        self.line_pul = self.chip_pul.get_line(1)
        self.line_pul.request(consumer="peri_pump", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        print("PUL引脚配置完成")