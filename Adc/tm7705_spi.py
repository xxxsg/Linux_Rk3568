#!/usr/bin/env python3
# Version: v1.4 - 完整TM7705增益配置交互版
import gpiod
import time
import sys

# ================= 配置区域 =================
# 硬件接线定义 (根据 gpiod 1.x 写法)
CHIP_CS_DIN_NAME = "gpiochip1"   # CS 和 DIN 所在的芯片名称
CHIP_SCK_DOUT_DRDY_NAME = "gpiochip3"  # SCK, DOUT, DRDY 所在的芯片名称

LINE_CS = 1      # CS 接 chip1 的 1 号引脚
LINE_DIN = 0     # DIN 接 chip1 的 0 号引脚
LINE_SCK = 5     # SCK 接 chip3 的 5 号引脚
LINE_DOUT = 4    # DOUT 接 chip3 的 4 号引脚
LINE_DRDY = 3    # DRDY 接 chip3 的 3 号引脚

# SPI配置参数
SPI_CLOCK_FREQ_HZ = 1000000  # SPI时钟频率 1MHz
SPI_CLOCK_PERIOD_SEC = 1.0 / SPI_CLOCK_FREQ_HZ
SPI_HALF_PERIOD = SPI_CLOCK_PERIOD_SEC / 2.0

# TM7705固定参数
VREF = 2.5  # 参考电压固定为2.5V (不可配置)

print(f"--- TM7705 ADC 控制启动 (gpiod 1.x) ---")
print(f"SPI时钟频率: {SPI_CLOCK_FREQ_HZ} Hz")
print(f"参考电压: {VREF} V")
print("----------------------------------")

# 全局变量
chip_cs_din = None
chip_sck_dout_drdy = None
line_cs = None
line_din = None
line_sck = None
line_dout = None
line_drdy = None

# 当前增益设置
current_gain = 1
current_channel = 0

def spi_init():
    """初始化SPI接口"""
    global chip_cs_din, chip_sck_dout_drdy, line_cs, line_din, line_sck, line_dout, line_drdy
    
    try:
        # 1. 打开 GPIO 芯片
        chip_cs_din = gpiod.Chip(f"/dev/{CHIP_CS_DIN_NAME}")
        chip_sck_dout_drdy = gpiod.Chip(f"/dev/{CHIP_SCK_DOUT_DRDY_NAME}")
        
        # 2. 获取线路对象
        line_cs = chip_cs_din.get_line(LINE_CS)
        line_din = chip_cs_din.get_line(LINE_DIN)
        line_sck = chip_sck_dout_drdy.get_line(LINE_SCK)
        line_dout = chip_sck_dout_drdy.get_line(LINE_DOUT)
        line_drdy = chip_sck_dout_drdy.get_line(LINE_DRDY)
        
        # 3. 请求线路控制权
        # CS, DIN, SCK 设置为输出
        line_cs.request(consumer="tm7705_cs", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])  # 默认高电平(禁用)
        line_din.request(consumer="tm7705_din", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])  # 默认低电平
        line_sck.request(consumer="tm7705_sck", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])  # 默认低电平
        
        # DOUT, DRDY 设置为输入
        line_dout.request(consumer="tm7705_dout", type=gpiod.LINE_REQ_DIR_IN)
        line_drdy.request(consumer="tm7705_drdy", type=gpiod.LINE_REQ_DIR_IN)
        
        print("SPI 初始化完成。")
        return True
        
    except Exception as e:
        print(f"SPI初始化失败: {e}")
        return False

def spi_write_byte(byte_value):
    """通过SPI发送一个字节数据"""
    # 拉低CS使能设备
    line_cs.set_value(0)
    
    # 发送8位数据 (MSB先发送)
    for i in range(7, -1, -1):
        # 设置DIN值
        bit = (byte_value >> i) & 0x01
        line_din.set_value(bit)
        
        # 产生SCK上升沿
        line_sck.set_value(1)
        time.sleep(SPI_HALF_PERIOD)
        
        # 产生SCK下降沿
        line_sck.set_value(0)
        time.sleep(SPI_HALF_PERIOD)
    
    # 拉高CS禁用设备
    line_cs.set_value(1)

def spi_read_byte():
    """通过SPI读取一个字节数据"""
    # 拉低CS使能设备
    line_cs.set_value(0)
    
    byte_value = 0
    # 读取8位数据 (MSB先读取)
    for i in range(7, -1, -1):
        # 产生SCK上升沿
        line_sck.set_value(1)
        time.sleep(SPI_HALF_PERIOD)
        
        # 读取DOUT值
        bit = line_dout.get_value()
        byte_value |= (bit << i)
        
        # 产生SCK下降沿
        line_sck.set_value(0)
        time.sleep(SPI_HALF_PERIOD)
    
    # 拉高CS禁用设备
    line_cs.set_value(1)
    
    return byte_value

def wait_for_ready(timeout_sec=1.0):
    """等待DRDY信号变为低电平（数据就绪）"""
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if line_drdy.get_value() == 0:  # DRDY低电平表示数据就绪
            return True
        time.sleep(0.001)  # 1ms间隔检查
    return False

def calculate_voltage_range(gain, unipolar=True):
    """
    计算指定增益下的电压测量范围
    返回: (min_volt, max_volt, description)
    """
    if unipolar:
        # 单极性: 0 到 Vref/gain
        min_volt = 0.0
        max_volt = VREF / gain
        desc = f"单极性: 0 ~ {max_volt:.3f}V"
    else:
        # 双极性: -Vref/gain 到 +Vref/gain
        min_volt = -VREF / gain
        max_volt = VREF / gain
        desc = f"双极性: ±{max_volt:.3f}V"
    
    return min_volt, max_volt, desc

def display_gain_options():
    """显示增益选项及其对应的电压范围"""
    print("\n=== TM7705 增益配置选项 ===")
    print("请选择增益值 (参考电压: 2.5V):")
    print("-" * 50)
    
    gain_options = [1, 2, 4, 8, 16, 32, 64, 128]
    
    for i, gain in enumerate(gain_options, 1):
        min_v, max_v, desc = calculate_voltage_range(gain, True)  # 默认单极性
        print(f"{i:2d}. 增益 {gain:3d}x -> {desc}")
    
    print("-" * 50)

def get_user_gain_selection():
    """获取用户增益选择"""
    gain_options = [1, 2, 4, 8, 16, 32, 64, 128]
    
    while True:
        try:
            display_gain_options()
            choice = input("\n请输入选项 (1-8) 或输入 'q' 退出: ")
            if choice.lower() == 'q':
                sys.exit(0)
            
            choice_num = int(choice)
            if 1 <= choice_num 