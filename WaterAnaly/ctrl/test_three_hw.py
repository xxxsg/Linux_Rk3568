"""三项硬件基础测试（独立脚本）。

依赖：
- board / busio / digitalio
- adafruit_tca9555
- adafruit_ads1x15

测试项：
1) GPIO 先低后高（中间 input 暂停）
2) TCA9555(0x20) P0~P10 先低后高（中间 input 暂停）
3) ADS1115 A0~A3 电压读取（mV）
"""

import board
import busio
import digitalio

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_tca9555


# ====== 按你的实际硬件改这里 ======
ADS1115_ADDR = 0x48
TCA9555_ADDR = 0x20

# 方式A：使用 board 命名引脚（推荐先试）
# 例如 "D5" / "GPIO1" / "IO1"，具体看你板级定义
GPIO_PIN_NAME = "GPIO1"

# 方式B：按 gpiod 思路直接填 chip/line（当方式A不可用时启用）
# 例如 gpiod 的 chip1 line1 -> gpiochip1, line 1
GPIO_CHIP = "gpiochip1"
GPIO_LINE = 1
# ==================================


def _get_pin_by_board_name(name):
    return getattr(board, name)


def _get_pin_by_chip_line(chip, line):
    """把 chip/line 转成 digitalio 可用的 Pin 对象。"""
    from adafruit_blinka.microcontroller.generic_linux.libgpiod_pin import Pin

    # 兼容不同 blinka 版本可能存在的 Pin 构造参数差异
    attempts = [
        ((), {"chip": chip, "line": line}),
        ((), {"chip": chip, "offset": line}),
        ((chip, line), {}),
        ((line, chip), {}),
    ]
    last_error = None
    for args, kwargs in attempts:
        try:
            return Pin(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"无法用 chip/line 构造 Pin: {last_error}")


def get_gpio_pin():
    print(f"[GPIO] 尝试方式A: board.{GPIO_PIN_NAME}")
    # 先尝试 board 名称
    try:
        pin = _get_pin_by_board_name(GPIO_PIN_NAME)
        print(f"[GPIO] 方式A成功，最终使用: board.{GPIO_PIN_NAME}")
        return pin
    except Exception as exc:
        print(f"[GPIO] 方式A失败: {exc}")

    print(f"[GPIO] 尝试方式B: chip={GPIO_CHIP}, line={GPIO_LINE}")
    # board 名称不可用时，回退到 chip/line
    pin = _get_pin_by_chip_line(GPIO_CHIP, GPIO_LINE)
    print(f"[GPIO] 方式B成功，最终使用: {GPIO_CHIP} line {GPIO_LINE}")
    return pin


def test_gpio_low_high():
    print("\n=== 1) GPIO 先低后高 ===")
    pin = get_gpio_pin()
    io = digitalio.DigitalInOut(pin)
    try:
        io.switch_to_output(value=False)
        print("GPIO 已设置为低电平")
        input("回车后设置为高电平...")
        io.value = True
        print("GPIO 已设置为高电平")
    finally:
        io.deinit()


def test_tca9555_low_high(i2c):
    print("\n=== 2) TCA9555(0x20) P0~P10 先低后高 ===")
    tca = adafruit_tca9555.TCA9555(i2c, address=TCA9555_ADDR)
    pins = []
    for pin_no in range(0, 11):
        p = tca.get_pin(pin_no)
        p.switch_to_output(value=False)
        pins.append(p)
    print("P0~P10 已全部设置为低电平")

    input("回车后将 P0~P10 全部设为高电平...")
    for p in pins:
        p.value = True
    print("P0~P10 已全部设置为高电平")


def test_ads_a0_a3(i2c):
    print("\n=== 3) 读取 ADS1115 A0~A3 电压 ===")
    ads = ADS.ADS1115(i2c, address=ADS1115_ADDR)
    ads.gain = 1

    channels = [
        ("A0", AnalogIn(ads, ADS.P0)),
        ("A1", AnalogIn(ads, ADS.P1)),
        ("A2", AnalogIn(ads, ADS.P2)),
        ("A3", AnalogIn(ads, ADS.P3)),
    ]
    for name, ch in channels:
        print(f"{name}: {ch.voltage * 1000.0:.2f} mV")


def main():
    i2c = busio.I2C(board.SCL, board.SDA)
    try:
        test_gpio_low_high()
        test_tca9555_low_high(i2c)
        test_ads_a0_a3(i2c)
        print("\n三项测试完成")
    finally:
        if hasattr(i2c, "deinit"):
            i2c.deinit()


if __name__ == "__main__":
    main()
