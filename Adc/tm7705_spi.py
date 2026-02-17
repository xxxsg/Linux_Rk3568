#!/usr/bin/env python3
# Version: v1.8 - 完整TM7705增益配置交互版（完整SPI配置版）
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
print(f"Version: v1.8")
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
    
    # 先检查初始状态
    initial_state = line_drdy.get_value()
    print(f"DRDY初始状态: {initial_state} ({'高电平' if initial_state else '低电平'})")
    
    start_time = time.time()
    check_count = 0
    
    while time.time() - start_time < timeout_sec:
        drdy_value = line_drdy.get_value()
        check_count += 1
        
        if drdy_value == 0:  # DRDY低电平表示数据就绪
            print(f"DRDY变为低电平，耗时: {(time.time() - start_time)*1000:.1f}ms, 检查次数: {check_count}")
            return True
        
        # 每100ms显示一次状态
        if check_count % 100 == 0:
            elapsed = time.time() - start_time
            print(f"等待中... {elapsed:.1f}s, DRDY状态: {drdy_value}")
        
        time.sleep(0.001)  # 1ms间隔检查
    
    print(f"超时：DRDY信号未变低 (检查次数: {check_count})")
    return False

def diagnose_drdy_issue():
    """诊断DRDY信号问题"""
    print("=== DRDY信号诊断 ===")
    
    if line_drdy is None:
        print("错误：DRDY线路未初始化")
        return False
    
    # 检查DRDY引脚配置
    print(f"DRDY引脚配置检查:")
    print(f"  芯片: {CHIP_SCK_DOUT_DRDY_NAME}")
    print(f"  引脚号: {LINE_DRDY}")
    
    # 连续监测DRDY状态
    print(f"\n连续监测DRDY状态 (5秒):")
    start_time = time.time()
    states = []
    timestamps = []
    
    while time.time() - start_time < 5.0:
        state = line_drdy.get_value()
        states.append(state)
        timestamps.append(time.time() - start_time)
        time.sleep(0.01)  # 10ms采样间隔
    
    # 分析结果
    high_count = states.count(1)
    low_count = states.count(0)
    total_samples = len(states)
    
    print(f"\n监测结果:")
    print(f"  总采样数: {total_samples}")
    print(f"  高电平次数: {high_count} ({high_count/total_samples*100:.1f}%)")
    print(f"  低电平次数: {low_count} ({low_count/total_samples*100:.1f}%)")
    
    if low_count == 0:
        print("警告：DRDY始终为高电平，可能存在以下问题:")
        print("  1. 硬件连接问题")
        print("  2. TM7705未正确上电")
        print("  3. 参考电压缺失")
        print("  4. 芯片故障")
        return False
    elif high_count == 0:
        print("注意：DRDY始终为低电平，可能是正常状态")
        return True
    else:
        print("DRDY信号有变化，可能是时序问题")
        return True


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
    """配置TM7705寄存器
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
        
        print(f"开始配置TM7705...")
        print(f"  目标配置: 通道{channel}, 增益{gain}x, {'单极性' if unipolar else '双极性'}模式")
        
        # TM7705配置序列
        # 1. 发送复位命令 (写通信寄存器)
        print("  步骤1: 发送复位命令")
        reset_cmd = 0x20  # 写通信寄存器命令
        spi_write_byte(reset_cmd)
        time.sleep(0.01)  # 等待稳定
        
        # 2. 配置设置寄存器
        print("  步骤2: 配置设置寄存器")
        # 构造设置寄存器值
        # 格式: MD1MD0xCH1CH0G2G1G0
        # MD1MD0: 工作模式 (01 = 自校准模式)
        # CH1CH0: 通道选择
        # G2G1G0: 增益选择
        setup_reg = 0x40  # 01000000 - 自校准模式, 通道0
        setup_reg |= (channel & 0x03) << 4  # 通道位
        
        # 增益映射
        gain_map = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5, 64: 6, 128: 7}
        if gain not in gain_map:
            raise ValueError(f"不支持的增益值: {gain}")
        setup_reg |= gain_map[gain]  # 增益位
        
        # 如果是双极性模式，设置相应位
        if not unipolar:
            setup_reg |= 0x80  # 设置双极性位
        
        print(f"  发送配置值: 0x{setup_reg:02X}")
        spi_write_byte(setup_reg)
        time.sleep(0.05)  # 等待配置生效
        
        # 3. 等待首次转换完成
        print("  步骤3: 等待首次转换完成")
        if wait_for_ready(2.0):  # 等待2秒
            print("  首次转换完成，DRDY信号正常")
        else:
            print("  警告：首次转换超时，但继续配置")
        
        print(f"TM7705配置完成:")
        print(f"  通道: {channel}")
        print(f"  增益: {gain}x")
        print(f"  模式: {'单极性' if unipolar else '双极性'}")
        
        # 显示电压范围
        min_v, max_v, desc = calculate_voltage_range(gain, unipolar)
        print(f"  测量范围: {desc}")
        
    except Exception as e:
        print(f"配置TM7705失败: {e}")
        raise


def tm7705_main():
    """TM7705主测试函数"""
    print("开始初始化TM7705...")
    
    if not spi_init():
        print("SPI初始化失败，退出")
        return
    
    # 初始化后先进行DRDY诊断
    print("\n=== 初始DRDY状态检查 ===")
    if not diagnose_drdy_issue():
        print("\n建议检查硬件连接和电源供应!")
        response = input("是否继续测试? (y/n): ")
        if response.lower() != 'y':
            cleanup_gpio()
            return
    
    try:
        # 获取用户增益选择
        selected_gain = get_user_gain_selection()
        
        # 配置TM7705
        configure_tm7705(selected_gain, 0, True)
        
        # 等待稳定
        time.sleep(0.1)
        
        print("\n=== TM7705测试 ===")
        
        # 连续读取测试
        print("\n连续读取测试 (10次):")
        voltages = []
        for i in range(10):
            data, voltage = read_tm7705_data()
            if data is not None:
                print(f"第{i+1:2d}次: 0x{data:04X} ({data:5d}), 电压: {voltage:8.4f}V")
                voltages.append(voltage)
            else:
                print(f"第{i+1:2d}次: 读取失败")
            time.sleep(0.5)
        
        # 统计信息
        if voltages:
            avg_voltage = sum(voltages) / len(voltages)
            min_voltage = min(voltages)
            max_voltage = max(voltages)
            print(f"\n统计信息:")
            print(f"  平均值: {avg_voltage:.4f}V")
            print(f"  最小值: {min_voltage:.4f}V")
            print(f"  最大值: {max_voltage:.4f}V")
            print(f"  波动范围: {max_voltage - min_voltage:.4f}V")
            
    except KeyboardInterrupt:
        print("\n用户中断")
        
    finally:
        # 释放资源
        cleanup_gpio()

if __name__ == "__main__":
    tm7705_main()