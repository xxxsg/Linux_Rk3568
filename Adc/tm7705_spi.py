#!/usr/bin/env python3
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
SPI_CLOCK_FREQ_HZ = 1000000  # SPI时钟频率 1MHz (可根据TM7705规格调整)
SPI_CLOCK_PERIOD_SEC = 1.0 / SPI_CLOCK_FREQ_HZ
SPI_HALF_PERIOD = SPI_CLOCK_PERIOD_SEC / 2.0

print(f"--- TM7705 ADC 控制启动 (gpiod 1.x) ---")
print(f"SPI时钟频率: {SPI_CLOCK_FREQ_HZ} Hz")
print(f"SPI时钟周期: {SPI_CLOCK_PERIOD_SEC:.6f} 秒")
print("----------------------------------")

# 全局变量
chip_cs_din = None
chip_sck_dout_drdy = None
line_cs = None
line_din = None
line_sck = None
line_dout = None
line_drdy = None

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

def read_tm7705_data():
    """读取TM7705的转换数据 (16位)"""
    try:
        # 等待数据就绪
        if not wait_for_ready():
            print("超时：DRDY信号未变低")
            return None
            
        # TM7705是16位ADC，读取16位数据
        # 读取时序：先发送读命令(0x00)，然后读取2个字节
        
        # 发送读命令 (0x00)
        spi_write_byte(0x00)
        
        # 读取16位数据 (2个字节)
        high_byte = spi_read_byte()
        low_byte = spi_read_byte()
        
        # 组合16位数据 (MSB first)
        data_16bit = (high_byte << 8) | low_byte
        
        return data_16bit
        
    except Exception as e:
        print(f"读取TM7705数据失败: {e}")
        return None


def read_tm7705_channel(channel=0):
    """读取指定通道的数据
    channel: 0 或 1 (TM7705有两个通道)
    """
    try:
        # 等待数据就绪
        if not wait_for_ready():
            print("超时：DRDY信号未变低")
            return None
            
        # 发送通道选择命令
        # 通道0: 0x08 (读取通道0)
        # 通道1: 0x09 (读取通道1)
        command = 0x08 | (channel & 0x01)
        spi_write_byte(command)
        
        # 读取16位数据
        high_byte = spi_read_byte()
        low_byte = spi_read_byte()
        
        # 组合16位数据
        data_16bit = (high_byte << 8) | low_byte
        
        return data_16bit
        
    except Exception as e:
        print(f"读取TM7705通道{channel}数据失败: {e}")
        return None


def tm7705_main():
    """TM7705主测试函数"""
    print("开始初始化TM7705...")
    
    if not spi_init():
        print("SPI初始化失败，退出")
        return
    
    try:
        print("\n=== TM7705测试 ===")
        
        # 测试读取通道0
        print("读取通道0数据...")
        data_ch0 = read_tm7705_channel(0)
        if data_ch0 is not None:
            print(f"通道0数据: 0x{data_ch0:04X} ({data_ch0})")
            
        # 测试读取通道1
        print("读取通道1数据...")
        data_ch1 = read_tm7705_channel(1)
        if data_ch1 is not None:
            print(f"通道1数据: 0x{data_ch1:04X} ({data_ch1})")
            
        # 连续读取测试
        print("\n连续读取测试 (10次):")
        for i in range(10):
            data = read_tm7705_data()
            if data is not None:
                print(f"第{i+1:2d}次: 0x{data:04X} ({data})")
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n用户中断")
        
    finally:
        # 释放资源
        if line_cs: line_cs.release()
        if line_din: line_din.release()
        if line_sck: line_sck.release()
        if line_dout: line_dout.release()
        if line_drdy: line_drdy.release()
        if chip_cs_din: chip_cs_din.close()
        if chip_sck_dout_drdy: chip_sck_dout_drdy.close()
        print("GPIO 资源已释放。")


if __name__ == "__main__":
    tm7705_main()