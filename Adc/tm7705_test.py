import gpiod
import time

print("=== TM7705 ADC 测试程序 V2 (gpiod 1.x兼容版) ===")

# === 配置参数 ===
# 注意：请根据你的实际开发板文档，确认这些GPIO芯片名是否正确！
# 例如，"gpiochip0" 是常见的芯片名，但你的板子可能是 "gpiochip4" 或其他。
CHIP_NAME_CS = "gpiochip1"  # CS 所在的芯片
CHIP_NAME_SCLK_DOUT_DRDY = "gpiochip3"  # SCK, DOUT, DRDY 所在的芯片

# TM7705 引脚连接到的RK3568 GPIO编号 (基于你提供的表格)
CS_PIN_OFFSET = 1      # CS 引脚 (片选) -> chip1, line1
SCLK_PIN_OFFSET = 5    # SCK 引脚 (时钟) -> chip3, line5
DIN_PIN_OFFSET = 0    # DIN 引脚 (数据输入) -> chip1, line0
DOUT_PIN_OFFSET = 4   # DOUT 引脚 (数据输出) -> chip3, line4
DRDY_PIN_OFFSET = 3   # DRDY 引脚 (数据就绪) -> chip3, line3

# TM7705 寄存器地址 (来自数据手册)
COMM_ADDR = 0x00  # 通信寄存器 (RS2=0, RS1=0, RS0=0)
SETUP_ADDR = 0x20  # 设置寄存器 (RS2=0, RS1=0, RS0=1)
CLOCK_ADDR = 0x40  # 时钟寄存器 (RS2=0, RS1=1, RS0=0)
DATA_ADDR = 0x60   # 数据寄存器 (RS2=0, RS1=1, RS0=1)

# TM7705 配置值 (增益=1, 双极性, 无缓冲, 50Hz更新率)
# 时钟寄存器 (CLOCK_ADDR): 假设 MCLK_IN = 2.4576MHz, 目标更新率为50Hz
#   - CLKDIS: 0 (启用时钟)
#   - CLKDIV: 0 (不除频)
#   - CLK: 1 (选择MCLK_IN频率)
#   - FS1: 0
#   - FS0: 0 (50Hz更新率)
#   所以 CLOCK_DATA = 0x10
CLOCK_DATA = 0x10

# 设置寄存器 (SETUP_ADDR): 增益=1, 双极性, 无缓冲
#   - MD1: 0 (正常模式)
#   - MD0: 0 (正常模式)
#   - G2: 0, G1: 0, G0: 0 (增益=1)
#   - B/U: 0 (双极性)
#   - BUF: 0 (无缓冲)
#   - FSYNC: 0 (正常)
#   所以 SETUP_DATA = 0x00
SETUP_DATA = 0x00

# === 全局变量 ===
cs_line = None
sclk_line = None
din_line = None
dout_line = None
drdy_line = None

def initialize_gpio():
    """
    初始化所有用于与TM7705通信的GPIO引脚。
    使用gpiod v1.x的API（与pump_control.py相同的写法）。
    """
    global cs_line, sclk_line, din_line, dout_line, drdy_line
    
    try:
        # 1. 打开 GPIO 芯片 (使用完整设备路径，参照 pump_control.py)
        chip_cs_din = gpiod.Chip(f"/dev/{CHIP_NAME_CS}")
        chip_sclk_dout_drdy = gpiod.Chip(f"/dev/{CHIP_NAME_SCLK_DOUT_DRDY}")

        # 2. 获取线路对象 (gpiod 1.x: get_line)
        cs_line = chip_cs_din.get_line(CS_PIN_OFFSET)
        din_line = chip_cs_din.get_line(DIN_PIN_OFFSET)
        sclk_line = chip_sclk_dout_drdy.get_line(SCLK_PIN_OFFSET)
        dout_line = chip_sclk_dout_drdy.get_line(DOUT_PIN_OFFSET)
        drdy_line = chip_sclk_dout_drdy.get_line(DRDY_PIN_OFFSET)

        # 3. 请求线路控制权 (gpiod 1.x: request)
        # 参数说明: consumer(使用者名称), type(方向), default_vals(初始值列表)
        # LINE_REQ_DIR_OUT = 1 (输出)
        # LINE_REQ_DIR_IN = 0 (输入)
        
        cs_line.request(consumer="tm7705_cs", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])  # 初始高电平
        sclk_line.request(consumer="tm7705_sclk", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])  # 初始低电平
        din_line.request(consumer="tm7705_din", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])  # 初始低电平
        
        # DOUT, DRDY 设置为输入
        dout_line.request(consumer="tm7705_dout", type=gpiod.LINE_REQ_DIR_IN)
        drdy_line.request(consumer="tm7705_drdy", type=gpiod.LINE_REQ_DIR_IN)

        print(f"✅ GPIO初始化成功!")
        print(f"   CS: {CHIP_NAME_CS}.{CS_PIN_OFFSET}, SCLK: {CHIP_NAME_SCLK_DOUT_DRDY}.{SCLK_PIN_OFFSET}")
        print(f"   DIN: {CHIP_NAME_CS}.{DIN_PIN_OFFSET}, DOUT: {CHIP_NAME_SCLK_DOUT_DRDY}.{DOUT_PIN_OFFSET}")
        print(f"   DRDY: {CHIP_NAME_SCLK_DOUT_DRDY}.{DRDY_PIN_OFFSET}")

    except Exception as e:
        print(f"❌ GPIO初始化失败: {e}")
        cleanup_gpio()
        raise

def send_bit_to_tm7705(bit):
    """
    向TM7705发送一个比特位 (bit)。
    bit: 0 或 1
    """
    print(f"📤 发送比特位: {bit}")  # 调试输出
    din_line.set_value(1 if bit else 0)  # 设置DIN
    time.sleep(0.000001)  # 微小延迟
    sclk_line.set_value(1)  # SCLK上升沿
    time.sleep(0.000001)  # 微小延迟
    sclk_line.set_value(0)  # SCLK下降沿
    time.sleep(0.000001)  # 微小延迟

def receive_bit_from_tm7705():
    """
    从TM7705接收一个比特位。
    返回: 接收到的比特位 (0 或 1)
    """
    sclk_line.set_value(1)  # SCLK上升沿
    time.sleep(0.000001)  # 微小延迟
    bit = dout_line.get_value()  # 读取DOUT
    print(f"📥 接收比特位: {bit}")  # 调试输出
    sclk_line.set_value(0)  # SCLK下降沿
    time.sleep(0.000001)  # 微小延迟
    return bit

def send_command_tm7705(command_byte, num_bits=8):
    """
    向TM7705发送一个命令字节 (command_byte)。
    command_byte: 要发送的字节
    num_bits: 要发送的比特数，默认8位
    """
    print(f"🔄 开始发送命令: 0x{command_byte:02X} ({num_bits}位)")
    
    # 拉低CS (选中TM7705)
    cs_line.set_value(0)
    print(f"   ✅ CS拉低 (选中)")

    # 发送命令字节的每一位 (MSB在前)
    for i in range(num_bits):
        bit = (command_byte >> (num_bits - 1 - i)) & 1
        send_bit_to_tm7705(bit)

    # 拉高CS (取消选中)
    cs_line.set_value(1)
    print(f"   ✅ CS拉高 (取消选中)")
    print(f"✅ 命令发送完成: 0x{command_byte:02X}")

def read_register_tm7705(num_bits=16):
    """
    从TM7705的寄存器中读取数据。
    num_bits: 要读取的比特数，默认16位 (TM7705数据寄存器)
    返回: 读取到的数值 (整数)
    """
    print(f"🔍 开始读取{num_bits}位数据")

    # 1. 发送读取命令 (地址+R/W=1)
    read_cmd = DATA_ADDR | 0x08
    send_command_tm7705(read_cmd, 8)  # 发送8位命令

    # 2. 读取数据
    cs_line.set_value(0)  # 重新拉低CS
    print(f"   ✅ CS拉低 (开始读取数据)")

    received_data = 0
    for i in range(num_bits):
        bit = receive_bit_from_tm7705()
        received_data = (received_data << 1) | bit

    cs_line.set_value(1)  # 拉高CS
    print(f"   ✅ CS拉高 (读取完成)")

    print(f"✅ 数据读取完成: 0x{received_data:04X} ({received_data})")
    return received_data

def wait_for_drdy_low():
    """
    等待DRDY引脚变为低电平 (表示数据已准备好)。
    """
    timeout_count = 0
    max_timeout = 1000000  # 最大超时次数 (约1秒)
    while drdy_line.get_value() == 1 and timeout_count < max_timeout:
        time.sleep(0.000001)  # 微小延迟
        timeout_count += 1
    if timeout_count >= max_timeout:
        print("⚠️  超时！等待DRDY变低失败。")
    else:
        print("✅ DRDY变为低电平，数据已准备就绪！")

def configure_tm7705():
    """
    配置TM7705芯片。
    步骤：
    1. 写入时钟寄存器 (CLOCK_ADDR)
    2. 写入设置寄存器 (SETUP_ADDR)
    3. 执行自校准 (Self-Calibration)
    """
    print("⚙️  开始配置TM7705...")

    # 1. 写入时钟寄存器
    print("   ⏱️  配置时钟寄存器...")
    send_command_tm7705(CLOCK_ADDR, 8)
    send_command_tm7705(CLOCK_DATA, 8)
    time.sleep(0.01)

    # 2. 写入设置寄存器
    print("   🔧  配置设置寄存器...")
    send_command_tm7705(SETUP_ADDR, 8)
    send_command_tm7705(SETUP_DATA, 8)
    time.sleep(0.01)

    # 3. 执行自校准 (修改MD0=1)
    print("   🔄  执行自校准...")
    setup_cal_data = 0x20  # MD0=1
    send_command_tm7705(SETUP_ADDR, 8)
    send_command_tm7705(setup_cal_data, 8)
    time.sleep(0.01)

    # 4. 等待校准完成
    wait_for_drdy_low()

    # 5. 恢复为正常模式
    print("   🛠️  恢复为正常模式...")
    send_command_tm7705(SETUP_ADDR, 8)
    send_command_tm7705(SETUP_DATA, 8)
    time.sleep(0.01)

    print("✅ TM7705配置和自校准完成！")

def main():
    """
    主程序入口。
    """
    try:
        # 1. 初始化GPIO
        print("1. 初始化GPIO...")
        initialize_gpio()

        # 2. 配置TM7705
        print("2. 配置TM7705...")
        configure_tm7705()

        # 3. 开始数据采集循环
        print("3. 开始数据采集循环...")
        print("\n🚀 开始数据采集...")
        sample_count = 0
        max_samples = 10

        while sample_count < max_samples:
            # 4. 等待数据就绪
            print(f"4. 等待数据就绪 ({sample_count+1}/{max_samples})...")
            wait_for_drdy_low()

            # 5. 读取数据
            print(f"5. 读取数据 ({sample_count+1}/{max_samples})...")
            raw_data = read_register_tm7705(num_bits=16)

            # 6. 处理原始数据
            print(f"6. 处理原始数据 ({sample_count+1}/{max_samples})...")
            voltage = (raw_data / 32767.0) * 2.5
            print(f"   📊 样本 {sample_count}: 原始值=0x{raw_data:04X} ({raw_data}), 电压={voltage:.4f} V")

            sample_count += 1
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 用户中断采集。")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
    finally:
        # 清理资源
        cleanup_gpio()
        print("\n🧹 GPIO资源已释放。")

def cleanup_gpio():
    """
    清理并释放所有GPIO资源。
    """
    global cs_line, sclk_line, din_line, dout_line, drdy_line
    if cs_line:
        cs_line.release()
    if sclk_line:
        sclk_line.release()
    if din_line:
        din_line.release()
    if dout_line:
        dout_line.release()
    if drdy_line:
        drdy_line.release()

if __name__ == "__main__":
    main()