import gpiod
import time

# 1. 打开芯片文件
# 注意：路径根据你的硬件平台可能是 /dev/gpiochip0, /dev/gpiochip1 等
chip = gpiod.Chip('/dev/gpiochip1')

# 2. 获取指定编号的 GPIO 线 (Line)
# 这里申请的是 GPIO 1
line_offset = 1
line = chip.get_line(line_offset)

# 3. 申请配置 (Request)
# consumer: 驱动中显示的名称
# type: 请求类型，gpiod.LINE_REQ_DIR_OUT 表示输出
# default_vals: 初始值列表 (0 或 1)
try:
    line.request(
        consumer='my-app',
        type=gpiod.LINE_REQ_DIR_OUT, # 这是 1.4 中设置输出的标准写法
        default_vals=[1]            # 初始值为 1 (高电平)
    )

    print(f"GPIO {line_offset} 已设置为输出并置高")

    # 保持高电平 1 秒
    time.sleep(1)

    # 修改值 (可选)
    # line.set_value(0) # 如果需要置低

finally:
    # 4. 释放资源 (非常重要，否则 GPIO 可能会被占用)
    line.release()
    chip.close()