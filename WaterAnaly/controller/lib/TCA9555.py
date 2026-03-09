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
TCA9555_DEFAULT_I2C_BUS = 1
TCA9555_DEFAULT_ADDR = 0x20

## TCA9555 Register addresses
TCA9555_REG_INPUT_PORT0 = 0x00
TCA9555_REG_INPUT_PORT1 = 0x01
TCA9555_REG_OUTPUT_PORT0 = 0x02
TCA9555_REG_OUTPUT_PORT1 = 0x03
TCA9555_REG_POLARITY_PORT0 = 0x04
TCA9555_REG_POLARITY_PORT1 = 0x05
TCA9555_REG_CONFIG_PORT0 = 0x06
TCA9555_REG_CONFIG_PORT1 = 0x07



class TCA9555():
    def __init__(self, i2c_bus=TCA9555_DEFAULT_I2C_BUS, addr=TCA9555_DEFAULT_ADDR):
        '''!
          @brief 初始化TCA9555控制器
          @param i2c_bus  I2C总线编号，默认为1
          @param addr  TCA9555设备地址，默认为0x20
        '''
        self.i2c_bus_num = i2c_bus
        self.addr = addr
        self.bus = None
        self.output_state = 0x0000  # 16-bit state for TCA9555
        self._open_i2c_bus()
        self._initialize_devices()
        # 默认初始化所有引脚为低电平
        self.initialize_all_pins(0)
    
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
            val = self.bus.read_byte_data(self.addr, TCA9555_REG_INPUT_PORT0)
            print(f"TCA9555 (0x{self.addr:02X}) connected, input=0x{val:02X}")
        except Exception as e:
            print(f"TCA9555 (0x{self.addr:02X}) connection failed: {e}")
    
    def set_all(self, state=0):
        '''!
          @brief 初始化所有TCA9555引脚为指定状态
          @param state  引脚状态: 0=低电平, 1=高电平
        '''
        if state not in [0, 1]:
            raise ValueError("State must be 0 (low) or 1 (high)")
        
        try:
            # 配置所有引脚为输出模式
            self.bus.write_byte_data(self.addr, TCA9555_REG_CONFIG_PORT0, 0x00)  # 0x00 = all outputs
            self.bus.write_byte_data(self.addr, TCA9555_REG_CONFIG_PORT1, 0x00)  # 0x00 = all outputs
            
            # 设置所有引脚状态
            pin_value = 0xFF if state == 1 else 0x00
            self.bus.write_byte_data(self.addr, TCA9555_REG_OUTPUT_PORT0, pin_value)
            self.bus.write_byte_data(self.addr, TCA9555_REG_OUTPUT_PORT1, pin_value)
            
            # 更新内部状态跟踪
            self.output_state = 0xFFFF if state == 1 else 0x0000
            
            state_str = "HIGH" if state == 1 else "LOW"
            print(f"All TCA9555 pins initialized to {state_str}")
            
        except Exception as e:
            print(f"Failed to initialize all TCA9555 pins: {e}")
            raise
    
    def set_some(self, state, pin_list):
        '''!
          @brief 设置指定列表中的TCA9555引脚为指定状态
          @param state  引脚状态: 0=低电平, 1=高电平
          @param pin_list  引脚编号列表，例如 [0, 1, 5, 8]
        '''
        if state not in [0, 1]:
            raise ValueError("State must be 0 (low) or 1 (high)")
        
        if not isinstance(pin_list, list):
            raise ValueError("pin_list must be a list of pin numbers")
        
        try:
            for pin_number in pin_list:
                if pin_number < 0 or pin_number > 15:
                    raise ValueError(f"Invalid pin number: {pin_number}. Must be 0-15")
                
                # 配置引脚为输出模式
                self._configure_tca9555_pin_output(pin_number)
                
                # 设置引脚状态
                if state == 1:
                    self.set_high(pin_number)
                else:
                    self.set_low(pin_number)
            
            state_str = "HIGH" if state == 1 else "LOW"
            print(f"TCA9555 pins {pin_list} set to {state_str}")
            
        except Exception as e:
            print(f"Failed to set some TCA9555 pins: {e}")
            raise
    
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
            config = self.bus.read_byte_data(self.addr, port_reg)
            
            # Set pin as output (clear bit)
            config_new = config & ~(1 << bit_pos)
            self.bus.write_byte_data(self.addr, port_reg, config_new)
            
            print(f"TCA9555 P{pin_number} configured as output")
            
        except Exception as e:
            print(f"Failed to configure TCA9555 P{pin_number} as output: {e}")
            raise
    
    def set_high(self, pin_number):
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
            output = self.bus.read_byte_data(self.addr, port_reg)
            
            # Set pin high (set bit)
            output_new = output | (1 << bit_pos)
            self.bus.write_byte_data(self.addr, port_reg, output_new)
            
            # Update internal state tracking (16-bit)
            if pin_number < 8:
                self.output_state = (self.output_state & 0xFF00) | output_new
            else:
                self.output_state = (self.output_state & 0x00FF) | (output_new << 8)
            
            print(f"TCA9555 P{pin_number} set to HIGH")
            
        except Exception as e:
            print(f"Failed to set TCA9555 P{pin_number} high: {e}")
            raise
    
    def set_low(self, pin_number):
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
            output = self.bus.read_byte_data(self.addr, port_reg)
            
            # Set pin low (clear bit)
            output_new = output & ~(1 << bit_pos)
            self.bus.write_byte_data(self.addr, port_reg, output_new)
            
            # Update internal state tracking (16-bit)
            if pin_number < 8:
                self.output_state = (self.output_state & 0xFF00) | output_new
            else:
                self.output_state = (self.output_state & 0x00FF) | (output_new << 8)
            
            print(f"TCA9555 P{pin_number} set to LOW")
            
        except Exception as e:
            print(f"Failed to set TCA9555 P{pin_number} low: {e}")
            raise
    
    def get_state(self, pin_number):
        '''!
          @brief 获取TCA9555引脚状态
          @param pin_number  引脚编号 (0-15)
          @return 如果引脚为高电平返回True，否则返回False
        '''
        # For TCA9555, we need to read the output register to check pin state
        try:
            port_reg = TCA9555_REG_OUTPUT_PORT0 if pin_number < 8 else TCA9555_REG_OUTPUT_PORT1
            bit_pos = pin_number % 8
            output = self.bus.read_byte_data(self.addr, port_reg)
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
                self.bus.write_byte_data(self.addr, TCA9555_REG_OUTPUT_PORT0, 0x00)
                self.bus.write_byte_data(self.addr, TCA9555_REG_OUTPUT_PORT1, 0x00)
                self.bus.close()
                print("I2C bus closed and TCA9555 reset")
            except Exception as e:
                print(f"Error during cleanup: {e}")
    
    def __del__(self):
        '''!
          @brief 析构函数，用于清理TCA9555资源
        '''
        self.cleanup()