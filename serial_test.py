#!/usr/bin/env python3
"""
串口通信测试脚本
支持 Linux 和 Windows，自动检测可用端口
"""

import serial
import serial.tools.list_ports
import time
import sys


def list_available_ports():
    """列出所有可用的串口"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("未找到可用串口")
        return []
    print("可用串口:")
    for port in ports:
        print(f"  {port.device} - {port.description}")
    return [p.device for p in ports]


def open_serial(port='/dev/ttyUSB0', baudrate=115200, timeout=1):
    """打开串口连接"""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_ONE,
            parity=serial.PARITY_NONE,
            xonxoff=False,
            rtscts=False,
            timeout=timeout
        )
        print(f"成功打开串口 {port} @ {baudrate}bps")
        return ser
    except serial.SerialException as e:
        print(f"打开串口失败: {e}")
        return None


def send_command(ser, cmd, hex_mode=False):
    """发送指令"""
    if hex_mode:
        data = bytes.fromhex(cmd.replace(' ', ''))
    else:
        if isinstance(cmd, str):
            data = cmd.encode('utf-8')
        else:
            data = cmd

    try:
        ser.write(data)
        print(f"发送: {data.hex() if hex_mode else cmd}")
        return True
    except serial.SerialException as e:
        print(f"发送失败: {e}")
        return False


def read_response(ser, size=1024, hex_mode=False):
    """读取响应"""
    try:
        if ser.in_waiting > 0:
            data = ser.read(min(size, ser.in_waiting))
            if hex_mode:
                print(f"接收: {data.hex()}")
            else:
                try:
                    print(f"接收: {data.decode('utf-8').strip()}")
                except UnicodeDecodeError:
                    print(f"接收: {data.hex()}")
            return data
        else:
            print("无数据")
            return None
    except serial.SerialException as e:
        print(f"读取失败: {e}")
        return None


def main():
    # 自动检测端口
    ports = list_available_ports()

    # 默认配置（Linux 常用端口）
    default_port = 'COM5'

    # 尝试使用默认端口
    port = default_port
    if ports and default_port not in ports:
        port = ports[0]
        print(f"使用可用端口: {port}")

    baudrate = 115200

    # 打开串口
    ser = open_serial(port, baudrate)
    if not ser:
        sys.exit(1)

    print("\n串口测试 - 输入指令发送，输入 q 退出")
    print("加 hex: 前缀切换十六进制模式, 例如: hex:01 02 03")
    print("-" * 40)

    try:
        while True:
            try:
                user_input = input("\n> ").strip()
            except EOFError:
                break

            if user_input.lower() == 'q':
                break

            if user_input.lower() == 'list':
                list_available_ports()
                continue

            # 检查是否是hex模式
            hex_mode = False
            if user_input.startswith('hex:'):
                hex_mode = True
                user_input = user_input[4:].strip()

            # 发送
            if user_input:
                send_command(ser, user_input, hex_mode)
                time.sleep(0.1)
                read_response(ser, hex_mode=hex_mode)

    except KeyboardInterrupt:
        print("\n中断退出")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("串口已关闭")


if __name__ == '__main__':
    main()
