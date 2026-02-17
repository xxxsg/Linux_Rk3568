#!/usr/bin/env python3
# Version: v2.0 - TM7705测试专用版（按标准流程）
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
print(f"Version: v2.0")
print(f"参考电压: {VREF} V")
print("重要提醒：TM7705的RESET引脚应连接5V/3.3V正电源")
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
INPUT_MODE = "unipolar"  # 输入模式: "unipolar" 或 "bipolar"

def cleanup_gpio():
    """清理GPIO资源"""
    global chip_cs_din, chip_sck_dout_drdy, line_cs, line_din, line_sck, line_dout, line_drdy
    
    try:
        if line_cs: 
            line_cs.set_value(1)  # 确保CS为高电平
            line_cs.release()
        if line_din: line_din.release()
        if line_sck: line_sck.release()
        if line_dout: line_dout.release()
        if line_drdy: line_drdy.release()
        if chip_cs_din: chip_cs_din.close()
        if chip_sck_dout_drdy: chip_sck_dout_drdy.close()
        print("GPIO 资源已释放。")
    except Exception as e:
        print(f"清理GPIO资源时出错: {e}")


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
    if line_cs is None or line_din is None or line_sck is None:
        raise RuntimeError("SPI线路未初始化")
    
    # 拉低CS使能设备
    line_cs.set_value(0)
    time.sleep(SPI_HALF_PERIOD)  # 确保CS稳定
    
    # 发送8位数据 (MSB先发送)
    for i in range(7, -1, -1):
        # 设置DIN值
        bit = (byte_value >> i) & 0x01
        line_din.set_value(bit)
        time.sleep(SPI_HALF_PERIOD / 2)  # 数据建立时间
        
        # 产生SCK上升沿
        line_sck.set_value(1)
        time.sleep(SPI_HALF_PERIOD)
        
        # 产生SCK下降沿
        line_sck.set_value(0)
        time.sleep(SPI_HALF_PERIOD)
    
    # 拉高CS禁用设备
    line_cs.set_value(1)
    time.sleep(SPI_HALF_PERIOD)  # CS恢复时间

def spi_read_byte():
    """通过SPI读取一个字节数据"""
    if line_cs is None or line_dout is None or line_sck is None:
        raise RuntimeError("SPI线路未初始化")
    
    # 拉低CS使能设备
    line_cs.set_value(0)
    time.sleep(SPI_HALF_PERIOD)  # 确保CS稳定
    
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
    time.sleep(SPI_HALF_PERIOD)  # CS恢复时间
    
    return byte_value

def wait_for_ready(timeout_sec=1.0):
    """等待DRDY信号变为低电平（数据就绪）"""
    if line_drdy is None:
        raise RuntimeError("DRDY线路未初始化")
    
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
            if 1 <= choice_num <= 8:
                selected_gain = gain_options[choice_num - 1]
                print(f"\n您选择了增益 {selected_gain}x")
                return selected_gain
            else:
                print("请输入 1-8 之间的数字！")
        except ValueError:
            print("请输入有效的数字！")
        except KeyboardInterrupt:
            print("\n用户中断")

def read_tm7705_data():
    """读取TM7705的转换数据 (16位)"""
    try:
        # 等待数据就绪
        if not wait_for_ready():
            print("超时：DRDY信号未变低")
            return None, None
            
        # 发送读命令 (0x38 + channel)
        read_cmd = 0x38 | (current_channel & 0x01)
        spi_write_byte(read_cmd)
        
        # 读取16位数据
        high_byte = spi_read_byte()
        low_byte = spi_read_byte()
        
        # 组合16位数据
        data_16bit = (high_byte << 8) | low_byte
        
        # 转换为电压值
        if INPUT_MODE == "unipolar":
            voltage = (data_16bit / 65535.0) * (VREF / current_gain)
        else:
            signed_data = data_16bit if data_16bit < 32768 else data_16bit - 65536
            voltage = (signed_data / 32768.0) * (VREF / current_gain)
        
        return data_16bit, voltage
        
    except Exception as e:
        print(f"读取TM7705数据失败: {e}")
        return None, None


def calibrate_zero_point():
    """校准零点 - 测量当前输入为0V时的读数"""
    print("开始零点校准，请确保输入为0V...")
    time.sleep(2)  # 给用户准备时间
    
    samples = []
    for i in range(10):
        data, voltage = read_tm7705_data()
        if data is not None:
            samples.append(data)
        time.sleep(0.1)
    
    if samples:
        zero_point = sum(samples) / len(samples)
        print(f"零点校准完成: {zero_point:.0f} (0x{int(zero_point):04X})")
        return int(zero_point)
    else:
        print("零点校准失败")
        return None

def configure_tm7705(gain, channel, unipolar=True):
    """配置TM7705寄存器 - 必须步骤！
    Args:
        gain: 增益值 (1, 2, 4, 8, 16, 32, 64, 128)
        channel: 通道号 (0或1)
        unipolar: True为单极性，False为双极性
    """
    global current_gain, current_channel, INPUT_MODE
    
    try:
        # 设置全局变量
        current_gain = gain
        current_channel = channel
        INPUT_MODE = "unipolar" if unipolar else "bipolar"
        
        print(f"=== TM7705配置开始 ===")
        print(f"目标配置: 通道{channel}, 增益{gain}x, {'单极性' if unipolar else '双极性'}模式")
        
        # 1. 发送复位命令
        print("1. 发送复位命令")
        reset_cmd = 0x20  # 写通信寄存器命令
        spi_write_byte(reset_cmd)
        time.sleep(0.01)
        
        # 2. 配置设置寄存器
        print("2. 配置设置寄存器")
        # 格式: MD1MD0xCH1CH0G2G1G0
        setup_reg = 0x40  # 01000000 - 自校准模式
        setup_reg |= (channel & 0x03) << 4  # 通道位
        
        # 增益映射
        gain_map = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5, 64: 6, 128: 7}
        if gain not in gain_map:
            raise ValueError(f"不支持的增益值: {gain}")
        setup_reg |= gain_map[gain]
        
        # 双极性模式设置
        if not unipolar:
            setup_reg |= 0x80
        
        print(f"发送配置值: 0x{setup_reg:02X}")
        spi_write_byte(setup_reg)
        time.sleep(0.05)
        
        print(f"✅ TM7705配置完成")
        print(f"芯片开始自动连续转换，DRDY将周期性变低")
        
    except Exception as e:
        print(f"❌ 配置TM7705失败: {e}")
        raise


def tm7705_main():
    """TM7705主测试函数"""
    print("开始初始化TM7705...")
    
    if not spi_init():
        print("SPI初始化失败，退出")
        return
    
    try:
        # 获取用户增益选择
        selected_gain = get_user_gain_selection()
        
        # 配置TM7705
        configure_tm7705(selected_gain, 0, True)
        
        # 等待稳定
        time.sleep(0.1)
        
        print("\n=== 等待DRDY信号周期性变低 ===")
        print("芯片已开始自动连续转换...")
        
        # 3. 等待并观察DRDY信号
        success_count = 0
        max_waits = 5
        
        for i in range(max_waits):
            print(f"\n3.{i+1} 等待第{i+1}次DRDY信号...")
            if wait_for_ready(2.0):  # 等待2秒
                success_count += 1
                print(f"✅ DRDY信号变低 - 第{success_count}次成功")
                
                # 4. 读取数据（可选，不影响DRDY）
                print("4. 读取数据")
                data, voltage = read_tm7705_data()
                if data is not None:
                    print(f"读取数据: 0x{data:04X} ({data}), 电压: {voltage:.4f}V")
                
                time.sleep(0.1)  # 等待下次转换
            else:
                print(f"❌ 等待超时")
                break
        
        print(f"\n=== 测试结果 ===")
        print(f"成功捕获DRDY信号: {success_count}/{max_waits}次")
        if success_count > 0:
            print("🎉 TM7705工作正常！")
        else:
            print("❌ TM7705可能存在问题，请检查硬件连接")
            
    except KeyboardInterrupt:
        print("\n用户中断")
        
    finally:
        # 释放资源
        cleanup_gpio()

if __name__ == "__main__":
    tm7705_main()