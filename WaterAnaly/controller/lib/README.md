# Controller Lib README

`controller/lib` 是控制器侧硬件驱动和设备封装库，主要包含：

- `ADS1115`：I2C ADC 驱动
- `TCA9555`：I2C GPIO 扩展器驱动
- `pins.py`：统一 GPIO/IO 引脚抽象
- `SoftSPI`：基于 `GpiodPin` 的软件 SPI
- `MAX31865`：RTD/PT100/PT1000 温度采集驱动
- `Stepper`：基于 `PUL/DIR/ENA` 的步进电机驱动
- `Pump`：基于 `Stepper` 的蠕动泵动作封装

## 导入方式

```python
from lib import (
    ADS1115,
    TCA9555,
    Pin,
    GpiodPin,
    Tca9555Pin,
    SoftSPI,
    MAX31865,
    Stepper,
    Pump,
)
```

## ADS1115

### 用途

用于读取 ADS1115 的单端或差分 ADC 值，并可直接换算为毫伏值。

### 示例

```python
from lib import ADS1115
from lib.ADS1115 import ADS1115_REG_CONFIG_PGA_4_096V

ads = ADS1115(i2c_bus=1, addr=0x48)
ads.ping()
ads.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)

raw = ads.read_raw(0)
mv = ads.read_voltage(0)

print("AIN0 raw =", raw)
print("AIN0 =", mv, "mV")

ads.close()
```

### 构造参数

`ADS1115(i2c_bus=1, addr=0x48)`

- `i2c_bus`：I2C 总线号，类型 `int`，要求 `>= 0`
- `addr`：I2C 地址，类型 `int`，范围 `0x03 ~ 0x77`

### 常用方法

`ping()`

- 作用：检测器件是否可通信
- 参数：无
- 返回：`bool`，正常通信时返回 `True`

`set_address(addr)`

- 作用：修改当前实例使用的 I2C 地址
- 参数：`addr: int`，范围 `0x03 ~ 0x77`
- 返回：无

`set_gain(gain)`

- 作用：设置 PGA 增益，同时影响电压换算系数
- 参数：`gain: int`，必须是 `ADS1115_REG_CONFIG_PGA_*` 常量之一
- 返回：无

`set_channel(channel)`

- 作用：校验并记录当前通道号
- 参数：`channel: int`，范围 `0 ~ 3`
- 返回：`int`，返回设置后的通道号

`read_raw(channel)`

- 作用：读取单端通道原始 ADC 值
- 参数：`channel: int`，范围 `0 ~ 3`
- 返回：`int`，16 位有符号原始值

`read_voltage(channel)`

- 作用：读取单端通道电压
- 参数：`channel: int`，范围 `0 ~ 3`
- 返回：`int`，单位 `mV`

`read_differential_raw(channel)`

- 作用：读取差分输入原始 ADC 值
- 参数：`channel: int`
  可选映射如下：
  `0 -> AIN0-AIN1`
  `1 -> AIN0-AIN3`
  `2 -> AIN1-AIN3`
  `3 -> AIN2-AIN3`
- 返回：`int`，16 位有符号原始值

`read_differential_voltage(channel)`

- 作用：读取差分输入电压
- 参数：`channel: int`，映射规则同上
- 返回：`int`，单位 `mV`

`close()`

- 作用：关闭 I2C 总线句柄
- 参数：无
- 返回：无

### 常用增益常量

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

## TCA9555

### 用途

用于控制 TCA9555 的 16 路 IO，包括方向配置、输出、输入读取和极性反转。

### 示例

```python
from lib import TCA9555

io = TCA9555(i2c_bus=1, addr=0x20)
io.ping()

io.set_mode([0, 1], "output")
io.write(0, True)
level = io.read(0, source="output")

print(level)

io.close()
```

### 构造参数

`TCA9555(i2c_bus=1, addr=0x20)`

- `i2c_bus`：I2C 总线号，类型 `int`
- `addr`：I2C 地址，类型 `int`

### 常用方法

`ping()`

- 作用：检测芯片是否可通信
- 参数：无
- 返回：`bool`

`set_mode(pins, mode)`

- 作用：设置一个或多个 IO 的方向
- 参数：`pins: int | list[int]`，引脚范围 `0 ~ 15`
- 参数：`mode: str`，只能是 `"input"` 或 `"output"`
- 返回：无

`write(pins, value)`

- 作用：给一个或多个 IO 输出电平
- 参数：`pins: int | list[int]`
- 参数：`value: bool | int`，允许 `True/False/1/0`
- 返回：无

`read(pins, source="input")`

- 作用：读取一个或多个 IO 的状态
- 参数：`pins: int | list[int]`
- 参数：`source: str`，`"input"` 读取输入寄存器，`"output"` 读取输出寄存器缓存
- 返回：传入单个 `int` 引脚时返回 `bool`；传入 `list[int]` 时返回 `list[bool]`

`write_port(port, value)`

- 作用：一次写入一个 8 位端口
- 参数：`port: int`，只能是 `0` 或 `1`
- 参数：`value: int`，范围 `0x00 ~ 0xFF`
- 返回：无

`read_port(port, source="input")`

- 作用：读取一个 8 位端口
- 参数：`port: int`，只能是 `0` 或 `1`
- 参数：`source: str`，`"input"` 或 `"output"`
- 返回：`int`，范围 `0x00 ~ 0xFF`

`write_word(value)`

- 作用：一次写入 16 位输出状态
- 参数：`value: int`，范围 `0x0000 ~ 0xFFFF`
- 返回：无

`read_word(source="input")`

- 作用：读取 16 位状态字
- 参数：`source: str`，`"input"` 或 `"output"`
- 返回：`int`，范围 `0x0000 ~ 0xFFFF`

`set_polarity(pins, inverted)`

- 作用：设置输入极性是否反转
- 参数：`pins: int | list[int]`
- 参数：`inverted: bool | int`
- 返回：无

`close()`

- 作用：关闭 I2C 总线句柄
- 参数：无
- 返回：无

## pins.py

### 用途

`pins.py` 提供统一引脚接口，方便上层代码不关心底层到底是 Linux GPIO 还是 TCA9555 扩展 IO。

### Pin 抽象接口

`Pin` 是抽象基类，常用接口如下：

`set_mode(mode, default_value=False)`

- 作用：设置引脚方向
- 参数：`mode: "input" | "output"`
- 参数：`default_value: bool`，仅输出模式时生效
- 返回：无

`set_output(default_value=False)`

- 作用：快捷设置为输出模式
- 参数：`default_value: bool`
- 返回：无

`set_input()`

- 作用：快捷设置为输入模式
- 参数：无
- 返回：无

`write(value)`

- 作用：输出高低电平
- 参数：`value: bool`
- 返回：无

`read()`

- 作用：读取当前逻辑电平
- 参数：无
- 返回：`bool`

`high()`

- 作用：等价于 `write(True)`
- 参数：无
- 返回：无

`low()`

- 作用：等价于 `write(False)`
- 参数：无
- 返回：无

`close()`

- 作用：释放底层资源
- 参数：无
- 返回：无

### GpiodPin

#### 用途

封装 Linux `libgpiod` 引脚。

#### 示例

```python
from lib import GpiodPin

pin = GpiodPin(
    pin=("/dev/gpiochip1", 1),
    consumer="pump_pul",
    active_high=True,
    default_value=False,
    mode="output",
)

pin.high()
pin.low()
pin.close()
```

#### 构造参数

`GpiodPin(pin, consumer="motorlib", active_high=True, default_value=False, mode="output")`

- `pin`：`tuple[str, int]`，格式为 `(chip, line)`，例如 `("/dev/gpiochip1", 1)`
- `consumer`：`str`，传给 libgpiod 的消费者名称
- `active_high`：`bool`，是否高电平表示逻辑 True
- `default_value`：`bool`，初始化为输出模式时的默认值
- `mode`：`"input"` 或 `"output"`

### Tca9555Pin

#### 用途

把 `TCA9555` 的单个 IO 封装成和 GPIO 类似的 `Pin` 对象，便于给 `Stepper` 这类模块复用。

#### 示例

```python
from lib import TCA9555, Tca9555Pin

io = TCA9555(i2c_bus=1, addr=0x20)

pin = Tca9555Pin(
    device=io,
    pin=11,
    active_high=True,
    initial_value=False,
    mode="output",
)

pin.high()
pin.low()

pin.close()
io.close()
```

#### 构造参数

`Tca9555Pin(device, pin, active_high=True, initial_value=False, mode="output")`

- `device`：`TCA9555` 实例
- `pin`：`int`，范围 `0 ~ 15`
- `active_high`：`bool`，是否高电平表示逻辑 True
- `initial_value`：`bool`，初始化为输出模式时的默认值
- `mode`：`"input"` 或 `"output"`

## SoftSPI

### 用途

`SoftSPI` 是基于 `Pin` 抽象的软件 SPI 实现，`sclk/mosi/miso/cs` 可以是任何实现了 `Pin` 接口的对象。

### 示例

```python
from lib import GpiodPin, SoftSPI

sclk = GpiodPin(("/dev/gpiochip0", 10), consumer="spi_sclk", mode="output")
mosi = GpiodPin(("/dev/gpiochip0", 11), consumer="spi_mosi", mode="output")
miso = GpiodPin(("/dev/gpiochip0", 12), consumer="spi_miso", mode="input")
cs = GpiodPin(("/dev/gpiochip1", 5), consumer="spi_cs", mode="output")

spi = SoftSPI(
    sclk=sclk,
    mosi=mosi,
    miso=miso,
    cs=cs,
)

rx = spi.transfer([0x80, 0x00])
print(rx)

spi.close()
cs.close()
miso.close()
mosi.close()
sclk.close()
```

### 构造参数

`SoftSPI(sclk, mosi, miso, cs)`

- `sclk`：`Pin`，时钟脚
- `mosi`：`Pin`，主发从收
- `miso`：`Pin`，主收从发
- `cs`：`Pin`，片选脚

### 常用方法

`cs_low()`

- 作用：拉低片选
- 参数：无
- 返回：无

`cs_high()`

- 作用：拉高片选
- 参数：无
- 返回：无

`transfer_byte(data)`

- 作用：发送 1 字节并读取 1 字节
- 参数：`data: int`
- 返回：`int`，范围 `0x00 ~ 0xFF`

`transfer(data)`

- 作用：连续收发多个字节
- 参数：`data: Iterable[int]`
- 返回：`list[int]`

`write(data)`

- 作用：仅发送数据，不关心返回值
- 参数：`data: Iterable[int]`
- 返回：无

`read(length, fill=0x00)`

- 作用：连续读取指定长度的数据
- 参数：`length: int`，要求 `>= 0`
- 参数：`fill: int`，读取时发送的填充值
- 返回：`list[int]`

`close()`

- 作用：关闭 SoftSPI 对象本身
- 参数：无
- 返回：无

## MAX31865

### 用途

用于读取 MAX31865 采集到的 RTD 原始值、电阻值和温度值。

### 示例

```python
from lib import GpiodPin, SoftSPI, MAX31865

sclk = GpiodPin(("/dev/gpiochip0", 10), consumer="spi_sclk", mode="output")
mosi = GpiodPin(("/dev/gpiochip0", 11), consumer="spi_mosi", mode="output")
miso = GpiodPin(("/dev/gpiochip0", 12), consumer="spi_miso", mode="input")
cs = GpiodPin(("/dev/gpiochip1", 5), consumer="spi_cs", mode="output")

spi = SoftSPI(
    sclk=sclk,
    mosi=mosi,
    miso=miso,
    cs=cs,
)

sensor = MAX31865(
    spi=spi,
    rref=430.0,
    r0=100.0,
    wires=2,
    filter_frequency=60,
)

temp_c = sensor.read_temperature()
resistance = sensor.read_resistance()
raw_rtd = sensor.read_raw_rtd()

print(temp_c)
print(resistance)
print(raw_rtd)

sensor.close()
cs.close()
miso.close()
mosi.close()
sclk.close()
```

### 构造参数

`MAX31865(spi, rref=430.0, r0=100.0, wires=2, filter_frequency=60)`

- `spi`：`SoftSPI` 实例
- `rref`：`float`，参考电阻阻值
- `r0`：`float`，RTD 在 0 摄氏度时的阻值，PT100 常用 `100.0`
- `wires`：`int`，只能是 `2`、`3`、`4`
- `filter_frequency`：`int`，只能是 `50` 或 `60`

### 常用方法

`read_temperature()`

- 作用：读取当前温度
- 参数：无
- 返回：`float`，单位摄氏度

`read_resistance()`

- 作用：读取当前 RTD 电阻
- 参数：无
- 返回：`float`，单位欧姆

`read_raw_rtd()`

- 作用：读取 15 位 RTD 原始 ADC 值
- 参数：无
- 返回：`int`

`read_fault()`

- 作用：读取故障状态寄存器
- 参数：无
- 返回：`int`

`clear_faults()`

- 作用：清除故障标志
- 参数：无
- 返回：无

`read_register(reg_addr)`

- 作用：读取单个寄存器
- 参数：`reg_addr: int`
- 返回：`int`

`read_registers(reg_addr, length)`

- 作用：连续读取多个寄存器
- 参数：`reg_addr: int`
- 参数：`length: int`
- 返回：`list[int]`

`write_register(reg_addr, value)`

- 作用：写单个寄存器
- 参数：`reg_addr: int`
- 参数：`value: int`
- 返回：无

`write_registers(reg_addr, values)`

- 作用：连续写多个寄存器
- 参数：`reg_addr: int`
- 参数：`values: list[int]`
- 返回：无

`close()`

- 作用：关闭底层 `SoftSPI`
- 参数：无
- 返回：无

### 换算辅助方法

这些方法不依赖实例状态，适合做离线计算：

`MAX31865.convert_adc_to_resistance(raw_adc, rref=430.0)`

- 作用：把原始 ADC 值换算成电阻
- 参数：`raw_adc: int`
- 参数：`rref: float`
- 返回：`float`

`MAX31865.convert_resistance_to_temperature(resistance, r0=100.0)`

- 作用：把 RTD 电阻换算成温度
- 参数：`resistance: float`
- 参数：`r0: float`
- 返回：`float`

`MAX31865.convert_adc_to_temperature(raw_adc, rref=430.0, r0=100.0)`

- 作用：把原始 ADC 值直接换算成温度
- 参数：`raw_adc: int`
- 参数：`rref: float`
- 参数：`r0: float`
- 返回：`float`

## Stepper

### 用途

`Stepper` 用统一的 `Pin` 接口驱动步进驱动器，支持定步数、定时长、连续运行和自动使能。

### 示例

```python
from lib import TCA9555, GpiodPin, Tca9555Pin, Stepper

io = TCA9555(i2c_bus=1, addr=0x20)

pul_pin = GpiodPin(("/dev/gpiochip1", 1), consumer="pump_pul", mode="output")
dir_pin = Tca9555Pin(io, 11, mode="output")
ena_pin = Tca9555Pin(io, 10, mode="output")

stepper = Stepper(
    pul_pin=pul_pin,
    dir_pin=dir_pin,
    ena_pin=ena_pin,
    steps_per_rev=800,
)

stepper.set_dir_active_level(True)
stepper.set_enable_active_level(True)
stepper.set_auto_enable(True)
stepper.set_rpm(300)
stepper.move_steps(1600, direction=True)

stepper.cleanup()
io.close()
```

### 构造参数

`Stepper(pul_pin, dir_pin, ena_pin=None, steps_per_rev=800)`

- `pul_pin`：`Pin`，脉冲输出脚
- `dir_pin`：`Pin`，方向控制脚
- `ena_pin`：`Pin | None`，使能脚，可选
- `steps_per_rev`：`int`，每圈步数，要求 `> 0`

### 配置方法

`set_dir_active_level(high_is_forward)`

- 作用：设置 DIR 高电平是否表示正转
- 参数：`high_is_forward: bool`
- 返回：无

`set_enable_active_level(low_is_enable)`

- 作用：设置 ENA 是否低电平有效
- 参数：`low_is_enable: bool`
- 返回：无

`set_auto_enable(enabled)`

- 作用：设置运动开始前自动使能、结束后自动失能
- 参数：`enabled: bool`
- 返回：无

`configure_driver(dir_high_forward=None, ena_low_enable=None, auto_enable=None)`

- 作用：批量配置驱动器逻辑
- 参数：三个参数都可为 `bool | None`
- 返回：无

`set_direction(forward)`

- 作用：设置当前运动方向
- 参数：`forward: bool`
- 返回：无

`set_rpm(rpm)`

- 作用：设置转速
- 参数：`rpm: float`
- 返回：无

`set_steps_per_rev(steps_per_rev)`

- 作用：修改每圈步数
- 参数：`steps_per_rev: int`
- 返回：无

### 运动方法

`enable()`

- 作用：使能驱动器
- 参数：无
- 返回：无

`disable()`

- 作用：关闭驱动器使能
- 参数：无
- 返回：无

`pulse_once()`

- 作用：输出一个完整脉冲
- 参数：无
- 返回：无

`move_steps(steps, direction=None)`

- 作用：按固定步数运动
- 参数：`steps: int`，要求 `>= 0`
- 参数：`direction: bool | None`，传入时会先设置方向
- 返回：无

`run_for_time(seconds, direction=None)`

- 作用：按固定时长运行
- 参数：`seconds: float`，要求 `> 0`
- 参数：`direction: bool | None`
- 返回：无

`run_continuous(direction=None)`

- 作用：持续运行，直到 `stop()` 或 `emergency_stop()`
- 参数：`direction: bool | None`
- 返回：无

`stop()`

- 作用：请求平滑停止，当前脉冲结束后退出
- 参数：无
- 返回：无

`emergency_stop()`

- 作用：立即停机并关闭使能
- 参数：无
- 返回：无

`cleanup()`

- 作用：执行急停并关闭关联引脚
- 参数：无
- 返回：无

## Pump

### 用途

`Pump` 是对 `Stepper` 的上层封装，把“正反转”转换成更符合蠕动泵语义的“吸液 / 排液”操作。

### 示例

```python
from lib import TCA9555, GpiodPin, Tca9555Pin, Stepper, Pump

io = TCA9555(i2c_bus=1, addr=0x20)

pul_pin = GpiodPin(("/dev/gpiochip1", 1), consumer="pump_pul", mode="output")
dir_pin = Tca9555Pin(io, 11, mode="output")
ena_pin = Tca9555Pin(io, 10, mode="output")

stepper = Stepper(
    pul_pin=pul_pin,
    dir_pin=dir_pin,
    ena_pin=ena_pin,
    steps_per_rev=800,
)
stepper.set_dir_active_level(True)
stepper.set_enable_active_level(True)
stepper.set_auto_enable(True)
stepper.set_rpm(300)

pump = Pump(
    driver=stepper,
    aspirate_direction="reverse",
)

pump.dispense_steps(800)
pump.aspirate_time(1.5)

pump.cleanup()
io.close()
```

### 构造参数

`Pump(driver, aspirate_direction="reverse")`

- `driver`：`Stepper` 实例
- `aspirate_direction`：吸液方向，`"forward"` 或 `"reverse"`

说明：

- 当 `aspirate_direction="forward"` 时，吸液使用步进正转，排液自动使用反转
- 当 `aspirate_direction="reverse"` 时，吸液使用步进反转，排液自动使用正转

### 常用方法

`dispense_steps(steps)`

- 作用：按步数排液
- 参数：`steps: int`，要求 `>= 0`
- 返回：无

`aspirate_steps(steps)`

- 作用：按步数吸液
- 参数：`steps: int`，要求 `>= 0`
- 返回：无

`dispense_revolutions(revolutions)`

- 作用：按圈数排液
- 参数：`revolutions: float`，要求 `> 0`
- 返回：无

`aspirate_revolutions(revolutions)`

- 作用：按圈数吸液
- 参数：`revolutions: float`，要求 `> 0`
- 返回：无

`dispense_time(seconds)`

- 作用：按时长排液
- 参数：`seconds: float`，要求 `> 0`
- 返回：无

`aspirate_time(seconds)`

- 作用：按时长吸液
- 参数：`seconds: float`，要求 `> 0`
- 返回：无

`dispense_continuous()`

- 作用：持续排液，直到 `stop()` 或 `emergency_stop()`
- 参数：无
- 返回：无

`aspirate_continuous()`

- 作用：持续吸液，直到 `stop()` 或 `emergency_stop()`
- 参数：无
- 返回：无

`stop()`

- 作用：请求平滑停止
- 参数：无
- 返回：无

`emergency_stop()`

- 作用：立即停机
- 参数：无
- 返回：无

`cleanup()`

- 作用：停止并清理底层 `Stepper`
- 参数：无
- 返回：无

## 使用建议

- `Stepper.cleanup()` 和 `Pump.cleanup()` 会关闭其持有的引脚对象；如果这些引脚还要给别的模块复用，不要过早调用
- `MAX31865.close()` 会关闭底层 `SoftSPI`；但不会自动关闭创建 `SoftSPI` 时传入的 `GpiodPin`
- `SoftSPI` 现在接受任何实现了 `Pin` 接口的对象，包括 `GpiodPin` 和 `Tca9555Pin`
- `Tca9555Pin.close()` 只是把这个包装对象标记为关闭，不会关闭底层 `TCA9555` 设备本身
