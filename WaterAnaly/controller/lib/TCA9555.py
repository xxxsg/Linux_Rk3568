'''!
  @file TCA9555.py
  @brief 提供树莓派TCA9555 I2C GPIO扩展器控制库。使用此库通过I2C控制GPIO输出。
  @copyright   Copyright (c) 2024 Your Company (http://www.yourcompany.com)
  @license     The MIT License (MIT)
  @author [Your Name](your.email@company.com)
  @version  V1.0
  @date  2024-01-01
  @url https://github.com/yourcompany/TCA9555
'''

import smbus2
import time

## I2C configuration
I2C_BUS_NUM = 1
TCA9555_ADDR = 0x20

## TCA9555 Register addresses
TCA9555_REG_INPUT_PORT0 = 0x00
TCA9555_REG_INPUT_PORT1 = 0x01
TCA9555_REG_OUTPUT_PORT0 = 0x02
TCA9555_REG_OUTPUT_PORT1 = 0x03
TCA9555_REG_POLARITY_PORT0 = 0x04
TCA9555_REG_POLARITY_PORT1 = 0x05
TCA9555_REG_CONFIG_PORT0 = 0x06
TCA9555_REG_CONFIG_PORT1 = 0x07

## Default settings
DEFAULT_VALVE_PIN = 2  # P2 pin

class TCA9555():
    def __init__(self, i2c_bus=I2C_BUS_NUM):
        '''!
          @brief 初始化TCA9555控制器
          @param i2c_bus  I2C总线编号，默认为1
        '''
        self.i2c_bus_num = i2c_bus
        self.bus = None
        self.output_state = 0x0000  # 16-bit state for TCA9555
        self._open_i2c_bus()
        self._initialize_devices()
    
    def _open_i2c_bus(self):
        '''!
          @brief 打开I2C总线
        '''
        try:
            self.bus = smbus2.SMBus(self.i2c_bus_num)
            print(f"Successfully opened I2C bus {self.i2c_bus_num}")
        except Exception as e:
            print(f"Failed to open I2C bus {self.i2c_bus_num}: {e}")
            raise
    
    def _initialize_devices(self):
        '''!
          @brief 初始化TCA9555设备
        '''
        print("Initializing TCA9555 device...")
        
        # Test TCA9555 communication
        try:
            val = self.bus.read_byte_data(TCA9555_ADDR, TCA9555_REG_INPUT_PORT0)
            print(f"✅ TCA9555 (0x{TCA9555_ADDR:02X}) connected, input=0x{val:02X}")
        except Exception as e:
            print(f"❌ TCA9555 (0x{TCA9555_ADDR:02X}) connection failed: {e}")
    
    def _configure_tca9555_pin_output(self, pin_number):
        '''!
          @brief 配置TCA9555引脚为输出模式
          @param pin_number  引脚编号 (0-15)
        '''
        if pin_number > 15:
            raise ValueError("TCA9555 pin number must be 0-15")
        
        try:
            # Determine which port (0 or 1)
            port_reg = TCA9555_REG_CONFIG_PORT0 if pin_number < 8 else TCA9555_REG_CONFIG_PORT1
            bit_pos = pin_number % 8
            
            # Read current configuration
            config = self.bus.read_byte_data(TCA9555_ADDR, port_reg)
            
            # Set pin as output (clear bit)
            config_new = config & ~(1 << bit_pos)
            self.bus.write_byte_data(TCA9555_ADDR, port_reg, config_new)
            
            print(f"TCA9555 P{pin_number} configured as output")
            
        except Exception as e:
            print(f"Failed to configure TCA9555 P{pin_number} as output: {e}")
            raise
    
    def set_tca9555_pin_high(self, pin_number):
        '''!
          @brief 设置TCA9555引脚为高电平
          @param pin_number  引脚编号 (0-15)
        '''
        if pin_number > 15:
            raise ValueError("TCA9555 pin number must be 0-15")
        
        # Configure pin as output if not already
        self._configure_tca9555_pin_output(pin_number)
        
        try:
            # Determine which port (0 or 1)
            port_reg = TCA9555_REG_OUTPUT_PORT0 if pin_number < 8 else TCA9555_REG_OUTPUT_PORT1
            bit_pos = pin_number % 8
            
            # Read current output state
            output = self.bus.read_byte_data(TCA9555_ADDR, port_reg)
            
            # Set pin high (set bit)
            output_new = output | (1 << bit_pos)
            self.bus.write_byte_data(TCA9555_ADDR, port_reg, output_new)
            
            # Update internal state tracking (16-bit)
            if pin_number < 8:
                self.output_state = (self.output_state & 0xFF00) | output_new
            else:
                self.output_state = (self.output_state & 0x00FF) | (output_new << 8)
            
            print(f"TCA9555 P{pin_number} set to HIGH")
            
        except Exception as e:
            print(f"Failed to set TCA9555 P{pin_number} high: {e}")
            raise
    
    def set_tca9555_pin_low(self, pin_number):
        '''!
          @brief 设置TCA9555引脚为低电平
          @param pin_number  引脚编号 (0-15)
        '''
        if pin_number > 15:
            raise ValueError("TCA9555 pin number must be 0-15")
        
        # Configure pin as output if not already
        self._configure_tca9555_pin_output(pin_number)
        
        try:
            # Determine which port (0 or 1)
            port_reg = TCA9555_REG_OUTPUT_PORT0 if pin_number < 8 else TCA9555_REG_OUTPUT_PORT1
            bit_pos = pin_number % 8
            
            # Read current output state
            output = self.bus.read_byte_data(TCA9555_ADDR, port_reg)
            
            # Set pin low (clear bit)
            output_new = output & ~(1 << bit_pos)
            self.bus.write_byte_data(TCA9555_ADDR, port_reg, output_new)
            
            # Update internal state tracking (16-bit)
            if pin_number < 8:
                self.output_state = (self.output_state & 0xFF00) | output_new
            else:
                self.output_state = (self.output_state & 0x00FF) | (output_new << 8)
            
            print(f"TCA9555 P{pin_number} set to LOW")
            
        except Exception as e:
            print(f"Failed to set TCA9555 P{pin_number} low: {e}")
            raise
    
    def open_solenoid_valve(self, pin_number=DEFAULT_VALVE_PIN):
        '''!
          @brief 打开电磁阀（设置TCA9555引脚高电平）
          @param pin_number  用于阀门控制的TCA9555引脚编号，默认为2 (P2)
        '''
        self.set_tca9555_pin_high(pin_number)
        print(f"Solenoid valve on TCA9555 P{pin_number} opened")
    
    def close_solenoid_valve(self, pin_number=DEFAULT_VALVE_PIN):
        '''!
          @brief 关闭电磁阀（设置TCA9555引脚低电平）
          @param pin_number  用于阀门控制的TCA9555引脚编号，默认为2 (P2)
        '''
        self.set_tca9555_pin_low(pin_number)
        print(f"Solenoid valve on TCA9555 P{pin_number} closed")
    
    def is_valve_open(self, pin_number=DEFAULT_VALVE_PIN):
        '''!
          @brief 检查电磁阀是否打开
          @param pin_number  用于阀门控制的TCA9555引脚编号，默认为2 (P2)
          @return 如果阀门打开（引脚高电平）返回True，否则返回False
        '''
        # For TCA9555, we need to read the output register to check pin state
        try:
            port_reg = TCA9555_REG_OUTPUT_PORT0 if pin_number < 8 else TCA9555_REG_OUTPUT_PORT1
            bit_pos = pin_number % 8
            output = self.bus.read_byte_data(TCA9555_ADDR, port_reg)
            return bool(output & (1 << bit_pos))
        except Exception as e:
            print(f"Failed to read TCA9555 P{pin_number} state: {e}")
            return False
    
    def cleanup(self):
        '''!
          @brief 清理I2C资源
        '''
        if self.bus:
            try:
                # Reset all TCA9555 outputs to low
                self.bus.write_byte_data(TCA9555_ADDR, TCA9555_REG_OUTPUT_PORT0, 0x00)
                self.bus.write_byte_data(TCA9555_ADDR, TCA9555_REG_OUTPUT_PORT1, 0x00)
                self.bus.close()
                print("I2C bus closed and TCA9555 reset")
            except Exception as e:
                print(f"Error during cleanup: {e}")
    
    def __del__(self):
        '''!
          @brief 析构函数，用于清理TCA9555资源
        '''
        self.cleanup()