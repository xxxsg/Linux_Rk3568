# Controller Lib README

`controller/lib` 提供控制层使用的硬件抽象接口。

- `ADS1115`：I2C ADC
- `TCA9555`：I2C GPIO 扩展器
- `SoftSPI`：基于 `gpiod` 的软件 SPI
- `MAX31865`：RTD 温度采集芯片
- `pins.py`：通用输出引脚抽象
- `stepper.py`：步进电机驱动
- `pump.py`：蠕动泵封装

## 导入

```python
from lib import TCA9555, GpiodPin, Tca9555Pin, Stepper, Pump
```

## ADS1115

```python
from lib import ADS1115
from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V

with ADS1115(i2c_bus=1, addr=0x48) as ads:
    ads.ping()
    ads.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
    mv = ads.read_voltage(0)
    print("AIN0 = %s mV" % mv)
```

常用接口：

- `ping()`：探测设备是否在线。成功返回 `True`，总线异常时抛出异常。
- `set_address(addr)`：设置 I2C 地址。`addr` 必须是 `int`，范围 `0x03~0x77`。
- `set_gain(gain)`：设置 PGA 增益。`gain` 必须是 `ADS1115_REG_CONFIG_PGA_*` 常量之一。
- `set_channel(channel)`：设置单端输入通道。`channel` 必须是 `int`，范围 `0~3`。返回设置后的通道号。
- `read_raw(channel)`：读取单端原始 ADC 值。`channel` 必须是 `int`，范围 `0~3`。返回有符号 `int`。
- `read_voltage(channel)`：读取单端电压值，单位 `mV`。`channel` 必须是 `int`，范围 `0~3`。返回 `int`。
- `read_differential_raw(channel)`：读取差分原始 ADC 值。`channel` 必须是 `int`，范围 `0~3`，内部会映射到芯片支持的差分组合。
- `read_differential_voltage(channel)`：读取差分电压值，单位 `mV`。`channel` 规则与 `read_differential_raw` 一致。
- `close()`：关闭 I2C 句柄。可重复调用。

构造参数：

- `ADS1115(i2c_bus=1, addr=0x48)`
- `i2c_bus`：I2C 总线号，必须是 `int >= 0`。
- `addr`：设备地址，必须是合法 I2C 7 位地址。

增益可选：

```python
from lib.ADS1115 import (
    ADS1115_REG_CONFIG_PGA_6_144V,
    ADS1115_REG_CONFIG_PGA_4_096V,
    ADS1115_REG_CONFIG_PGA_2_048V,
    ADS1115_REG_CONFIG_PGA_1_024V,
    ADS1115_REG_CONFIG_PGA_0_512V,
    ADS1115_REG_CONFIG_PGA_0_256V,
)
```

- `ADS1115_REG_CONFIG_PGA_6_144V`
- `ADS1115_REG_CONFIG_PGA_4_096V`
- `ADS1115_REG_CONFIG_PGA_2_048V`
- `ADS1115_REG_CONFIG_PGA_1_024V`
- `ADS1115_REG_CONFIG_PGA_0_512V`
- `ADS1115_REG_CONFIG_PGA_0_256V`

## TCA9555

```python
from lib import TCA9555

with TCA9555(i2c_bus=1, addr=0x20) as io:
    io.ping()
    io.set_mode([0, 1], "output")
    io.write(0, True)
    level = io.read(0, source="output")
    print(level)
```

常用接口：

- `ping()`：探测设备是否在线。成功时返回 `True`，总线异常时抛出异常。
- `set_mode(pins, mode)`：设置 IO 方向。`pins` 必须是 `int` 或 `list[int]`，引脚范围 `0~15`，不允许空列表，重复引脚会自动去重。`mode` 只能是 `"input"` 或 `"output"`。
- `write(pins, value)`：写输出电平。`pins` 规则同 `set_mode`。`value` 必须是 `bool`、`0` 或 `1`。
- `read(pins, source="input")`：读取一个或多个引脚电平。`source` 只能是 `"input"` 或 `"output"`。如果传单个引脚，返回 `bool`；如果传多个引脚，返回 `list[bool]`。
- `write_port(port, value)`：按 8 位端口写入。`port` 只能是 `0` 或 `1`。`value` 必须是 `int`，范围 `0x00~0xFF`。
- `read_port(port, source="input")`：读取 8 位端口值。`port` 只能是 `0` 或 `1`。`source` 只能是 `"input"` 或 `"output"`。返回 `int`。
- `write_word(value)`：一次写入 16 位输出值。`value` 必须是 `int`，范围 `0x0000~0xFFFF`。
- `read_word(source="input")`：一次读取 16 位值。`source` 只能是 `"input"` 或 `"output"`。返回 `int`。
- `set_polarity(pins, inverted)`：设置输入极性翻转。`pins` 规则同 `set_mode`。`inverted` 必须是 `bool`、`0` 或 `1`。
- `close()`：关闭 I2C 句柄。可重复调用。

构造参数：

- `TCA9555(i2c_bus=1, addr=0x20)`
- `i2c_bus`：I2C 总线号，建议传合法的 `int >= 0`。
- `addr`：设备地址，建议传合法 I2C 7 位地址。

## SoftSPI

```python
from lib import SoftSPI

with SoftSPI(
    sclk=("/dev/gpiochip0", 10),
    mosi=("/dev/gpiochip0", 11),
    miso=("/dev/gpiochip0", 12),
    cs=("/dev/gpiochip1", 5),
) as spi:
    rx = spi.transfer([0x80, 0x00])
    print(rx)
```

常用接口：

- `cs_low()`：将片选拉低。总线关闭后不可调用。
- `cs_high()`：将片选拉高。总线关闭后不可调用。
- `transfer_byte(data)`：发送 1 个字节并接收 1 个字节。`data` 会先转成 `int`，再按 `0xFF` 截断。返回范围 `0~255` 的 `int`。
- `transfer(data)`：连续发送多个字节。`data` 必须是 `list[int]`。每个元素都会按 `0xFF` 截断。返回长度相同的 `list[int]`。
- `close()`：释放所有 GPIO line 和 chip 句柄。可重复调用。

引脚约束：

- `SoftSPI(sclk, mosi, miso, cs)`
- 每个引脚参数都必须是 `(chip, line)` 二元组。
- `chip` 必须是非空 `str`，例如 `"/dev/gpiochip1"`。
- `line` 必须是 `int >= 0`。

## MAX31865

```python
from lib import SoftSPI, MAX31865

with SoftSPI(
    sclk=("/dev/gpiochip0", 10),
    mosi=("/dev/gpiochip0", 11),
    miso=("/dev/gpiochip0", 12),
    cs=("/dev/gpiochip1", 5),
) as spi:
    with MAX31865(
        spi,
        rref=430.0,
        r0=100.0,
        wires=2,
        filter_frequency=60,
    ) as sensor:
        print(sensor.temperature)
```

直接取值：

- `sensor.temperature`：直接读取当前温度值，单位摄氏度，返回 `float`。
- `sensor.resistance`：直接读取当前电阻值，返回 `float`。
- `sensor.raw_rtd`：直接读取当前原始 RTD ADC 值，返回 `int`。

常用接口：

- `read_fault()`：读取当前故障寄存器，返回 `int`。
- `clear_faults()`：清除故障标志。
- `read_register(reg_addr)`：读取单个寄存器。`reg_addr` 应为寄存器地址整数。
- `read_registers(reg_addr, length)`：连续读取多个寄存器。`reg_addr` 应为整数，`length` 建议为 `int > 0`。返回 `list[int]`。
- `write_register(reg_addr, value)`：写单个寄存器。`reg_addr` 和 `value` 应为整数，写入时会按 `0xFF` 截断。
- `write_registers(reg_addr, values)`：连续写多个寄存器。`values` 必须是 `list[int]`，每个元素都会按 `0xFF` 截断。
- `adc_to_resistance(raw_adc)`：按当前实例的 `rref` 把 ADC 值换算为电阻值。返回 `float`。
- `resistance_to_temperature(resistance)`：按当前实例的 `r0` 把电阻值换算为摄氏温度。`resistance` 必须大于 `0`。返回 `float`。
- `calculate_temperature(raw_adc)`：按当前实例的 `rref` 和 `r0`，直接把原始 ADC 值换算为温度。返回 `float`。
- `close()`：关闭设备。当前实现也会同时关闭底层 `spi`。

静态/类方法换算接口：

- `MAX31865.convert_adc_to_resistance(raw_adc, rref=430.0)`：静态方法，不依赖实例。
- `MAX31865.convert_resistance_to_temperature(resistance, r0=100.0)`：静态方法，不依赖实例。
- `MAX31865.convert_adc_to_temperature(raw_adc, rref=430.0, r0=100.0)`：类方法，不依赖实例。

构造参数：

- `MAX31865(spi, rref=430.0, r0=100.0, wires=2, filter_frequency=60)`
- `spi`：不能是 `None`，应传入 `SoftSPI` 实例。
- `rref`：参考电阻值，通常是板上参考电阻阻值。
- `r0`：RTD 在 0 摄氏度时的标称电阻，例如 PT100 常用 `100.0`。
- `wires`：只能是 `2`、`3`、`4`，表示热电阻接线方式。
- `filter_frequency`：只能是 `50` 或 `60`，表示工频滤波设置。`50` 适用于 50Hz 工频环境，`60` 适用于 60Hz 工频环境。

## pins.py

### OutputPin

- `OutputPin`：输出引脚抽象接口，主要方法是 `write(value)`、`high()`、`low()`、`close()`。

### GpiodPin

```python
from lib import GpiodPin

pin = GpiodPin(
    pin=("/dev/gpiochip1", 1),
    consumer="pump_pul",
    active_high=True,
    default_value=False,
)
```

构造参数：

- `pin`：必须是 `(chip, line)`，其中 `chip` 是非空 `str`，`line` 是 `int >= 0`。
- `consumer`：必须是非空 `str`，用于 gpiod 请求资源时标识调用方。
- `active_high`：`True` 表示逻辑高对应物理高电平，`False` 表示逻辑高会翻转成物理低电平。
- `default_value`：初始输出值，按逻辑值解释。

常用接口：

- `write(value)`：写逻辑电平。`value` 按 `bool` 解释。
- `high()`：输出逻辑高。
- `low()`：输出逻辑低。
- `close()`：释放 gpiod line 和 chip 资源。

### Tca9555Pin

```python
from lib import TCA9555, Tca9555Pin

with TCA9555(i2c_bus=1, addr=0x20) as io:
    pin = Tca9555Pin(
        device=io,
        pin=11,
        active_high=True,
        initial_value=False,
    )
```

构造参数：

- `device`：不能是 `None`，应传入 `TCA9555` 实例。
- `pin`：必须是 `int`，范围 `0~15`。
- `active_high`：`True` 表示逻辑高对应物理高电平，`False` 表示逻辑高会翻转成物理低电平。
- `initial_value`：初始化后立即写入的逻辑值。

常用接口：

- `write(value)`：写逻辑电平。内部会根据 `active_high` 自动翻转。
- `high()`：输出逻辑高。
- `low()`：输出逻辑低。
- `close()`：标记关闭。注意它不会关闭底层整个 `TCA9555` 设备。

## Stepper

引入示例：

```python
from lib import TCA9555, GpiodPin, Tca9555Pin, Stepper

with TCA9555(i2c_bus=1, addr=0x20) as io:
    stepper = Stepper(
        pul_pin=GpiodPin(("/dev/gpiochip1", 1), consumer="pump_pul"),
        dir_pin=Tca9555Pin(io, 11),
        ena_pin=Tca9555Pin(io, 10),
        steps_per_rev=800,
    )
    stepper.set_rpm(300)
    stepper.set_direction(True)
    stepper.move_steps(1600)
```

构造参数：

- `Stepper(pul_pin, dir_pin, ena_pin=None, steps_per_rev=800, dir_high_forward=True, ena_low_enable=True, auto_enable=True)`
- `pul_pin` 和 `dir_pin` 必须是 `OutputPin` 实例，且不能为 `None`。
- `ena_pin` 可以是 `None`，也可以是 `OutputPin` 实例。
- `steps_per_rev` 必须是 `int > 0`。
- `dir_high_forward`、`ena_low_enable`、`auto_enable` 都是 `bool` 型开关。

核心接口：

- `enable()`：使能驱动输出。如果 `ena_pin is None`，只会修改内部状态。
- `disable()`：关闭驱动输出。如果 `ena_pin is None`，只会修改内部状态。
- `set_direction(forward)`：设置方向。`forward` 必须是 `bool`，`True` 表示正转，`False` 表示反转。
- `set_rpm(rpm)`：设置运行转速。`rpm` 必须是数字且大于 `0`。
- `set_steps_per_rev(steps_per_rev)`：设置每转步数。`steps_per_rev` 必须是 `int > 0`。
- `pulse_once()`：输出一个完整脉冲周期。脉冲宽度优先使用 `pulse_high_s/pulse_low_s`，否则根据 `rpm` 和 `steps_per_rev` 自动计算。
- `move_steps(steps, direction=None)`：按步数运行。`steps` 必须是 `int >= 0`。`direction` 必须是 `bool` 或 `None`。
- `run_for_time(seconds, direction=None)`：按时长运行。`seconds` 必须是大于 `0` 的数字。`direction` 必须是 `bool` 或 `None`。
- `run_continuous(direction=None)`：持续运行，直到调用 `stop()` 或 `emergency_stop()`。`direction` 必须是 `bool` 或 `None`。
- `stop()`：请求当前动作优雅停止。会在运动循环的下一次检查点退出，不会主动立即失能驱动。
- `emergency_stop()`：立即停止，并调用 `disable()` 关闭驱动输出，适合急停场景。
- `cleanup()`：先执行 `emergency_stop()`，再关闭绑定的全部引脚。

运行时常改属性：

- `rpm`：当前转速，建议始终保持大于 `0`。
- `pulse_high_s` / `pulse_low_s`：可选的自定义高低电平持续时间，单位秒。如果只设置一边，另一边会复用同一个值。显式设置时必须是大于 `0` 的数字。

## Pump

引入示例：

```python
from lib import TCA9555, GpiodPin, Tca9555Pin, Stepper, Pump

with TCA9555(i2c_bus=1, addr=0x20) as io:
    stepper = Stepper(
        pul_pin=GpiodPin(("/dev/gpiochip1", 1), consumer="pump_pul"),
        dir_pin=Tca9555Pin(io, 11),
        ena_pin=Tca9555Pin(io, 10),
        steps_per_rev=800,
    )
    stepper.set_rpm(300)

    pump = Pump(stepper)
    pump.dispense_revolutions(2.0)
    pump.aspirate_for_time(1.5)
```

构造参数：

- `Pump(driver, dispense_direction="forward", aspirate_direction="reverse", prime_direction=None, purge_direction=None)`
- `driver` 不能是 `None`，通常应传入 `Stepper` 实例。
- 所有方向参数都只能是 `"forward"` 或 `"reverse"`。
- `prime_direction` 为 `None` 时，会跟随 `dispense_direction`。
- `purge_direction` 为 `None` 时，当前实现也会跟随 `dispense_direction`。

常用接口：

- `dispense_revolutions(revolutions)`：按圈数执行出液。`revolutions` 必须是大于 `0` 的数字。
- `aspirate_revolutions(revolutions)`：按圈数执行吸液。`revolutions` 规则同上。
- `dispense_for_time(seconds)`：按时间执行出液。`seconds` 必须是大于 `0` 的数字。
- `aspirate_for_time(seconds)`：按时间执行吸液。`seconds` 规则同上。
- `prime(seconds)`：按时间执行预充。`seconds` 必须是大于 `0` 的数字。
- `purge(seconds)`：按时间执行排空。`seconds` 必须是大于 `0` 的数字。
- `run_continuous_dispense()`：持续出液，直到停止。
- `run_continuous_aspirate()`：持续吸液，直到停止。
- `stop()`：把停止请求转发到底层驱动。
- `emergency_stop()`：把急停请求转发到底层驱动。
- `cleanup()`：关闭底层驱动以及关联引脚资源。
