"""硬件基础联调测试（按当前接线规划）。

仅保留 3 项：
1) digitalio 控制 GPIO1：先拉低，按回车后拉高
2) TCA9555(0x20) 的 0~10 引脚：先全低，按回车后全高
3) ADS1115 A0~A3 电压读取（mV）

原来的流程联调测试场景已停用（按需求注释掉/不执行）。
"""

import board
import busio
import digitalio

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_tca9555

from config import ADS1115_I2C_ADDR

GPIO1_PIN_NAME = "GPIO1"
VALVE_TCA9555_ADDR = 0x20


def _get_board_pin(pin_name):
    try:
        return getattr(board, pin_name)
    except AttributeError as exc:
        raise ValueError(f"board pin not found: {pin_name!r}") from exc


def test_gpio1_digitalio():
    print("\n=== 1) digitalio 控制 GPIO1 ===")
    gpio = digitalio.DigitalInOut(_get_board_pin(GPIO1_PIN_NAME))
    try:
        gpio.switch_to_output(value=False)
        print(f"{GPIO1_PIN_NAME} 已设置为低电平")
        input("回车后将 GPIO1 设置为高电平...")
        gpio.value = True
        print(f"{GPIO1_PIN_NAME} 已设置为高电平")
    finally:
        gpio.deinit()


def test_tca9555_valve_0_to_10(i2c):
    print("\n=== 2) TCA9555(0x20) 控制 0~10 引脚 ===")
    tca = adafruit_tca9555.TCA9555(i2c, address=VALVE_TCA9555_ADDR)
    pins = []

    for pin_no in range(0, 11):
        pin = tca.get_pin(pin_no)
        pin.switch_to_output(value=False)
        pins.append(pin)
    print("0~10 引脚已全部设置为低电平")

    input("回车后将 0~10 引脚全部设置为高电平...")
    for pin in pins:
        pin.value = True
    print("0~10 引脚已全部设置为高电平")


def test_ads1115_a0_to_a3(i2c):
    print("\n=== 3) 读取 ADS1115 A0~A3 电压 ===")
    ads = ADS.ADS1115(i2c, address=ADS1115_I2C_ADDR)
    ads.gain = 1

    channels = [
        ("A0", AnalogIn(ads, ADS.P0)),
        ("A1", AnalogIn(ads, ADS.P1)),
        ("A2", AnalogIn(ads, ADS.P2)),
        ("A3", AnalogIn(ads, ADS.P3)),
    ]
    for name, ch in channels:
        print(f"{name}: {ch.voltage * 1000.0:.2f} mV")


def test_all():
    i2c = busio.I2C(board.SCL, board.SDA)
    try:
        test_gpio1_digitalio()
        test_tca9555_valve_0_to_10(i2c)
        test_ads1115_a0_to_a3(i2c)
        print("\n全部基础联调测试执行完成")
    finally:
        if hasattr(i2c, "deinit"):
            i2c.deinit()


if __name__ == "__main__":
    test_all()
