'''!
  @file DFRobot_ADS1115.py
  @brief 提供树莓派ADS1115 I2C ADC读取库。使用此库读取模拟电压值。
  @copyright   Copyright (c) 2010 DFRobot Co.Ltd (http://www.dfrobot.com)
  @license     The MIT License (MIT)
  @author [luoyufeng](yufeng.luo@dfrobot.com)
  @version  V1.0
  @date  2019-06-19
  @url https://github.com/DFRobot/DFRobot_ADS1115
'''

import smbus
import time

## ==================== I2C地址 ====================
ADS1115_IIC_ADDRESS0				= 0x48  # 默认I2C地址
ADS1115_IIC_ADDRESS1				= 0x49  # 备用I2C地址

## ==================== 默认配置 ====================
ADS1115_DEFAULT_BUS = 1
ADS1115_DEFAULT_ADDR = ADS1115_IIC_ADDRESS0

## ==================== 寄存器地址 ====================
## 转换寄存器
ADS1115_REG_POINTER_CONVERT			= 0x00 
## 配置寄存器
ADS1115_REG_POINTER_CONFIG			= 0x01 
## 低阈值寄存器
ADS1115_REG_POINTER_LOWTHRESH		= 0x02 
## 高阈值寄存器
ADS1115_REG_POINTER_HITHRESH		= 0x03 

## ==================== 配置寄存器位域 ====================
## 操作状态位(OS)
ADS1115_REG_CONFIG_OS_NOEFFECT		= 0x00  # 无效果
ADS1115_REG_CONFIG_OS_SINGLE		= 0x80  # 开始单次转换

## 多路复用器配置(MUX) - 差分输入
ADS1115_REG_CONFIG_MUX_DIFF_0_1		= 0x00  # AIN0 vs AIN1 (默认)
ADS1115_REG_CONFIG_MUX_DIFF_0_3		= 0x10  # AIN0 vs AIN3
ADS1115_REG_CONFIG_MUX_DIFF_1_3		= 0x20  # AIN1 vs AIN3
ADS1115_REG_CONFIG_MUX_DIFF_2_3		= 0x30  # AIN2 vs AIN3

## 多路复用器配置(MUX) - 单端输入
ADS1115_REG_CONFIG_MUX_SINGLE_0		= 0x40  # AIN0 vs GND
ADS1115_REG_CONFIG_MUX_SINGLE_1		= 0x50  # AIN1 vs GND
ADS1115_REG_CONFIG_MUX_SINGLE_2		= 0x60  # AIN2 vs GND
ADS1115_REG_CONFIG_MUX_SINGLE_3		= 0x70  # AIN3 vs GND

## 可编程增益放大器(PGA)
ADS1115_REG_CONFIG_PGA_6_144V		= 0x00  # ±6.144V range = Gain 2/3
ADS1115_REG_CONFIG_PGA_4_096V		= 0x02  # ±4.096V range = Gain 1
ADS1115_REG_CONFIG_PGA_2_048V		= 0x04  # ±2.048V range = Gain 2 (默认)
ADS1115_REG_CONFIG_PGA_1_024V		= 0x06  # ±1.024V range = Gain 4
ADS1115_REG_CONFIG_PGA_0_512V		= 0x08  # ±0.512V range = Gain 8
ADS1115_REG_CONFIG_PGA_0_256V		= 0x0A  # ±0.256V range = Gain 16

## 工作模式(MODE)
ADS1115_REG_CONFIG_MODE_CONTIN		= 0x00  # 连续转换模式
ADS1115_REG_CONFIG_MODE_SINGLE		= 0x01  # 单次转换模式 (默认)

## 数据速率(DR)
ADS1115_REG_CONFIG_DR_8SPS			= 0x00  # 8 samples per second
ADS1115_REG_CONFIG_DR_16SPS			= 0x20  # 16 samples per second
ADS1115_REG_CONFIG_DR_32SPS			= 0x40  # 32 samples per second
ADS1115_REG_CONFIG_DR_64SPS			= 0x60  # 64 samples per second
ADS1115_REG_CONFIG_DR_128SPS		= 0x80  # 128 samples per second (默认)
ADS1115_REG_CONFIG_DR_250SPS		= 0xA0  # 250 samples per second
ADS1115_REG_CONFIG_DR_475SPS		= 0xC0  # 475 samples per second
ADS1115_REG_CONFIG_DR_860SPS		= 0xE0  # 860 samples per second

## 比较器模式(CMODE)
ADS1115_REG_CONFIG_CMODE_TRAD		= 0x00  # 传统比较器 (默认)
ADS1115_REG_CONFIG_CMODE_WINDOW		= 0x10  # 窗口比较器

## 比较器极性(CPOL)
ADS1115_REG_CONFIG_CPOL_ACTVLOW		= 0x00  # ALERT/RDY pin低电平有效 (默认)
ADS1115_REG_CONFIG_CPOL_ACTVHI		= 0x08  # ALERT/RDY pin高电平有效

## 比较器锁存(CLAT)
ADS1115_REG_CONFIG_CLAT_NONLAT		= 0x00  # 非锁存 (默认)
ADS1115_REG_CONFIG_CLAT_LATCH		= 0x04  # 锁存

## 比较器队列(CQUE)
ADS1115_REG_CONFIG_CQUE_1CONV		= 0x00  # 1次转换后触发
ADS1115_REG_CONFIG_CQUE_2CONV		= 0x01  # 2次转换后触发
ADS1115_REG_CONFIG_CQUE_4CONV		= 0x02  # 4次转换后触发
ADS1115_REG_CONFIG_CQUE_NONE		= 0x03  # 禁用比较器 (默认) 


class ADS1115():
	def __init__(self, bus_num=ADS1115_DEFAULT_BUS, addr=ADS1115_DEFAULT_ADDR):
		'''!
		  @brief 初始化ADS1115 ADC
		  @param bus_num  I2C总线号，默认为1
		  @param addr  I2C设备地址，默认为0x48
		'''
		self.bus = smbus.SMBus(bus_num)
		self.addr = addr
		self.gain = ADS1115_REG_CONFIG_PGA_2_048V  # 默认增益
		self.coefficient = 0.0625  # 默认系数对应PGA_2_048V
		self.channel = 0
	
	def set_gain(self,gain):
		'''!
		  @brief 设置增益和输入电压范围。
		  @param gain  配置可编程增益放大器
		  @n ADS1115_REG_CONFIG_PGA_6_144V     = 0x00 # 6.144V range = Gain 2/3
		  @n ADS1115_REG_CONFIG_PGA_4_096V     = 0x02 # 4.096V range = Gain 1
		  @n ADS1115_REG_CONFIG_PGA_2_048V     = 0x04 # 2.048V range = Gain 2
		  @n 默认:
		  @n ADS1115_REG_CONFIG_PGA_1_024V     = 0x06 # 1.024V range = Gain 4
		  @n ADS1115_REG_CONFIG_PGA_0_512V     = 0x08 # 0.512V range = Gain 8
		  @n ADS1115_REG_CONFIG_PGA_0_256V     = 0x0A # 0.256V range = Gain 16
		'''
		self.gain = gain
		if self.gain == ADS1115_REG_CONFIG_PGA_6_144V:
			self.coefficient = 0.1875
		elif self.gain == ADS1115_REG_CONFIG_PGA_4_096V:
			self.coefficient = 0.125
		elif self.gain == ADS1115_REG_CONFIG_PGA_2_048V:
			self.coefficient = 0.0625
		elif self.gain == ADS1115_REG_CONFIG_PGA_1_024V:
			self.coefficient = 0.03125
		elif self.gain == ADS1115_REG_CONFIG_PGA_0_512V:
			self.coefficient = 0.015625
		elif self.mygain == ADS1115_REG_CONFIG_PGA_0_256V:
			self.coefficient = 0.0078125
		else:
			self.coefficient = 0.125
	def set_addr_ADS1115(self,addr):
		'''!
		  @brief 设置I2C地址。
		  @param addr  7位I2C地址，范围是1~127。
		'''
		self.addr = addr
	def set_channel(self,channel):
		'''!
		  @brief 选择用户要使用的通道0-3。
		  @param channel  通道: 0-3
		  @n 单端输出: 
		  @n    0 : AINP = AIN0 且 AINN = GND
		  @n    1 : AINP = AIN1 且 AINN = GND
		  @n    2 : AINP = AIN2 且 AINN = GND
		  @n    3 : AINP = AIN3 且 AINN = GND
		  @n 差分输出:
		  @n    0 : AINP = AIN0 且 AINN = AIN1
		  @n    1 : AINP = AIN0 且 AINN = AIN3
		  @n    2 : AINP = AIN1 且 AINN = AIN3
		  @n    3 : AINP = AIN2 且 AINN = AIN3
		  @return channel
		'''
		self.channel = channel
		while self.channel > 3 :
			self.channel = 0
		
		return self.channel
	
	def set_single(self):
		'''!
		  @brief 使用单次读取进行配置。
		'''
		if self.channel == 0:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_SINGLE_0 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		elif self.channel == 1:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_SINGLE_1 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		elif self.channel == 2:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_SINGLE_2 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		elif self.channel == 3:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_SINGLE_3 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		
		self.bus.write_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONFIG, CONFIG_REG)
	
	def set_differential(self):
		'''!
		  @brief 配置为比较器输出。
		'''
		if self.channel == 0:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_DIFF_0_1 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		elif self.channel == 1:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_DIFF_0_3 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		elif self.channel == 2:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_DIFF_1_3 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		elif self.channel == 3:
			CONFIG_REG = [ADS1115_REG_CONFIG_OS_SINGLE | ADS1115_REG_CONFIG_MUX_DIFF_2_3 | self.gain | ADS1115_REG_CONFIG_MODE_CONTIN, ADS1115_REG_CONFIG_DR_128SPS | ADS1115_REG_CONFIG_CQUE_NONE]
		
		self.bus.write_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONFIG, CONFIG_REG)
	
	def read_value(self):
		'''!
		  @brief  读取ADC值。
		  @return raw  adc
		'''
		data = self.bus.read_i2c_block_data(self.addr, ADS1115_REG_POINTER_CONVERT, 2)
		
		# Convert the data
		raw_adc = data[0] * 256 + data[1]
		
		if raw_adc > 32767:
			raw_adc -= 65535
		raw_adc = int(float(raw_adc)*self.coefficient)
		return {'r' : raw_adc}

	def read_voltage(self,channel):
		'''!
		  @brief 读取指定通道的电压。
		  @param channel  通道: 0-3
		  @n 单端输出: 
		  @n    0 : AINP = AIN0 且 AINN = GND
		  @n    1 : AINP = AIN1 且 AINN = GND
		  @n    2 : AINP = AIN2 且 AINN = GND
		  @n    3 : AINP = AIN3 且 AINN = GND
		  @n 差分输出:
		  @n    0 : AINP = AIN0 且 AINN = AIN1
		  @n    1 : AINP = AIN0 且 AINN = AIN3
		  @n    2 : AINP = AIN1 且 AINN = AIN3
		  @n    3 : AINP = AIN2 且 AINN = AIN3
		  @return Voltage
		'''
		self.set_channel(channel)
		self.set_single()
		time.sleep(0.1)
		return self.read_value()

	def comparator_voltage(self,channel):
		'''!
		  @brief 设置比较器使ALERT/RDY引脚触发。
		  @param channel  通道: 0-3
		  @n 单端输出: 
		  @n    0 : AINP = AIN0 且 AINN = GND
		  @n    1 : AINP = AIN1 且 AINN = GND
		  @n    2 : AINP = AIN2 且 AINN = GND
		  @n    3 : AINP = AIN3 且 AINN = GND
		  @n 差分输出:
		  @n    0 : AINP = AIN0 且 AINN = AIN1
		  @n    1 : AINP = AIN0 且 AINN = AIN3
		  @n    2 : AINP = AIN1 且 AINN = AIN3
		  @n    3 : AINP = AIN2 且 AINN = AIN3
		  @return Voltage
		'''
		self.set_channel(channel)
		self.set_differential()
		time.sleep(0.1)
		return self.read_value()