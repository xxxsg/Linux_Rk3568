#!/usr/bin/env python3
import gpiod
import time
import sys

# ================= 配置区域 =================
# 硬件接线定义 (根据 gpiod 1.x 写法)
CHIP_PUL_ENA_NAME = "gpiochip1"  # PUL 和 ENA 所在的芯片名称
CHIP_DIR_NAME     = "gpiochip3"  # DIR 所在的芯片名称

LINE_PUL = 1  # PUL 接 chip1 的 1 号引脚 -> 控制转速
LINE_DIR = 5  # DIR 接 chip3 的 5 号引脚 -> 控制转向
LINE_ENA = 0  # ENA 接 chip1 的 0 号引脚 -> 控制启停

# 电机参数设置
SUBDIVISION = 800       # 驱动器拨码开关设置的细分 (脉冲/转)
TARGET_RPM = 300        # 【已修改】目标转速调整为 300 RPM
RUN_TIME_SEC = 5        # 运行持续时间 (秒)

# 计算脉冲频率
# 公式: 频率(Hz) = (转速 RPM * 细分) / 60
# 300 / 60 = 5 转/秒
# 5 * 800 = 4000 Hz
TARGET_FREQ = (TARGET_RPM * SUBDIVISION) / 60.0
PERIOD_SEC = 1.0 / TARGET_FREQ
HALF_PERIOD = PERIOD_SEC / 2.0

print(f"--- 蠕动泵控制启动 (gpiod 1.x) ---")
print(f"细分设置: {SUBDIVISION} 脉冲/转")
print(f"目标转速: {TARGET_RPM} RPM")
print(f"计算频率: {TARGET_FREQ:.2f} Hz")
print(f"运行时间: {RUN_TIME_SEC} 秒")
print("----------------------------------")

chip_pul_ena = None
chip_dir = None
line_pul = None
line_dir = None
line_ena = None

try:
    # 1. 打开 GPIO 芯片 (使用完整设备路径，参照 app.py)
    chip_pul_ena = gpiod.Chip(f"/dev/{CHIP_PUL_ENA_NAME}")
    chip_dir = gpiod.Chip(f"/dev/{CHIP_DIR_NAME}")

    # 2. 获取线路对象 (gpiod 1.x: get_line)
    line_pul = chip_pul_ena.get_line(LINE_PUL)
    line_dir = chip_dir.get_line(LINE_DIR)
    line_ena = chip_pul_ena.get_line(LINE_ENA)

    # 3. 请求线路控制权 (gpiod 1.x: request)
    # 参数说明: consumer(使用者名称), type(方向), default_val(初始值)
    # LINE_REQ_DIR_OUT = 1 (输出)
    # LINE_REQ_DIR_IN = 0 (输入)
    
    line_pul.request(consumer="pump_pul", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
    line_dir.request(consumer="pump_dir", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1]) # 1=正转
    line_ena.request(consumer="pump_ena", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0]) # 0=低电平使能
    
    print("GPIO 初始化完成，电机已使能。")
    time.sleep(0.5)

    # 4. 开始发送脉冲
    start_time = time.time()
    pulse_count = 0
    
    print(f"开始旋转 ({TARGET_RPM} RPM)...")

    while (time.time() - start_time) < RUN_TIME_SEC:
        # 产生方波
        line_pul.set_value(1)
        time.sleep(HALF_PERIOD)
        
        line_pul.set_value(0)
        time.sleep(HALF_PERIOD)
        
        pulse_count += 1

    print(f"停止旋转。总脉冲数: {pulse_count}")
    
    # 5. 禁用电机 (高电平禁用)
    line_ena.set_value(1)
    print("电机已禁用。")

except KeyboardInterrupt:
    print("\n用户中断，正在停止...")
    if line_ena:
        line_ena.set_value(1)

except Exception as e:
    print(f"发生错误: {e}")
    print("提示: 请检查芯片名称是否正确 (使用 gpioinfo 查看)，以及是否有 sudo 权限。")

finally:
    # 释放资源 (gpiod 1.x: release)
    if line_pul: line_pul.release()
    if line_dir: line_dir.release()
    if line_ena: line_ena.release()
    if chip_pul_ena: chip_pul_ena.close()
    if chip_dir: chip_dir.close()
    print("GPIO 资源已释放。")