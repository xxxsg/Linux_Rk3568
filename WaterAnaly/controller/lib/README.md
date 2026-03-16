# Controller Lib README

这个目录存放控制器侧的硬件驱动类，主要包括：

- `ADS1115`：I2C ADC 采样
- `TCA9555`：I2C GPIO 扩展
- `SoftSPI`：基于 `gpiod` 的软件 SPI
- `MAX31865`：RTD 温度采集
- `PeriPump`：蠕动泵控制

## 依赖关系

- `ADS1115` 依赖 `smbus2` 或 `smbus`
- `TCA9555` 依赖 `smbus2`
- `SoftSPI` 依赖 `gpiod`
- `MAX31865` 依赖一个 SPI 对象，当前可直接配合 `SoftSPI`
- `PeriPump` 依赖 `gpiod` 和一个 `TCA9555` 实例

## 快速示例

### ADS1115

```python
from lib.ADS1115 import ADS1115, ADS1115_REG_CONFIG_PGA_4_096V

with ADS1115(bus_num=1, addr=0x48) as ads:
    ads.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)
    mv = ads.read_voltage(0)
    print(f"AIN0 = {mv} mV")
```

### TCA9555

```python
from lib.TCA9555 import TCA9555

with TCA9555(i2c_bus=1, addr=0x20) as io:
    io.set_mode([0, 1], "output")
    io.write(0, True)
    level = io.read(0, source="output")
    print(level)
```

### SoftSPI + MAX31865

```python
from lib.SoftSPI import SoftSPI
from lib.MAX31865 import MAX31865

with SoftSPI(
    sclk=("/dev/gpiochip0", 10),
    mosi=("/dev/gpiochip0", 11),
    miso=("/dev/gpiochip0", 12),
    cs=("/dev/gpiochip1", 5),
) as spi:
    with MAX31865(spi, rref=430.0, r0=100.0) as sensor:
        print(sensor.temperature)
```

### PeriPump

```python
from lib.TCA9555 import TCA9555
from lib.PeriPump import PeriPump

with TCA9555(i2c_bus=1, addr=0x20) as io:
    pump = PeriPump(
        tca9555_instance=io,
        pul_chip="/dev/gpiochip1",
        pul_line=1,
        dir_pin=11,
        ena_pin=10,
    )
    pump.set_rpm(300)
    pump.set_direction(1)
    pump.run_by_time(3)
    pump.cleanup()
```

## ADS1115

### 类定义

```python
class ADS1115:
    def __init__(self, bus_num: int = ADS1115_DEFAULT_BUS, addr: int = ADS1115_DEFAULT_ADDR)
```

### 公开接口

- `set_address(addr: int) -> None`
  - 设置 I2C 地址
- `set_gain(gain: int) -> None`
  - 设置 PGA 增益和输入量程
- `set_channel(channel: int) -> int`
  - 设置默认通道，返回归一化后的通道号
- `read_raw(channel: int) -> int`
  - 读取单端输入原始 ADC 值
- `read_voltage(channel: int) -> int`
  - 读取单端输入电压，单位毫伏
- `read_differential_raw(channel: int) -> int`
  - 读取差分输入原始 ADC 值
- `read_differential_voltage(channel: int) -> int`
  - 读取差分输入电压，单位毫伏
- `close() -> None`
  - 关闭 I2C 句柄

### 常用量程常量

- `ADS1115_REG_CONFIG_PGA_6_144V`
- `ADS1115_REG_CONFIG_PGA_4_096V`
- `ADS1115_REG_CONFIG_PGA_2_048V`
- `ADS1115_REG_CONFIG_PGA_1_024V`
- `ADS1115_REG_CONFIG_PGA_0_512V`
- `ADS1115_REG_CONFIG_PGA_0_256V`

## TCA9555

### 类定义

```python
class TCA9555:
    def __init__(self, i2c_bus: int = TCA9555_DEFAULT_I2C_BUS, addr: int = TCA9555_DEFAULT_ADDR)
```

### 公开接口

- `ping() -> bool`
  - 通过一次寄存器读取确认设备在线
- `set_mode(pin_or_pins: int | list[int], mode: Literal["input", "output"]) -> None`
  - 设置单个或多个 IO 方向
- `write(pin_or_pins: int | list[int], value: bool | int) -> None`
  - 写单个或多个 IO 输出电平
- `read(pin_or_pins: int | list[int], source: Literal["input", "output"] = "input") -> bool | list[bool]`
  - 读取单个或多个 IO 电平
- `write_port(port: int, value: int) -> None`
  - 按 8 位端口写输出
- `read_port(port: int, source: Literal["input", "output"] = "input") -> int`
  - 按 8 位端口读输入或输出锁存值
- `write_word(value: int) -> None`
  - 一次写 16 位输出字
- `read_word(source: Literal["input", "output"] = "input") -> int`
  - 一次读 16 位输入或输出字
- `set_polarity(pin_or_pins: int | list[int], inverted: bool | int) -> None`
  - 设置输入极性反转
- `close() -> None`
  - 关闭 I2C 句柄

## SoftSPI

### 类型定义

```python
PinSpec = tuple[str, int]
```

### 类定义

```python
class SoftSPI:
    def __init__(self, sclk: PinSpec, mosi: PinSpec, miso: PinSpec, cs: PinSpec)
```

### 公开接口

- `cs_low() -> None`
  - 拉低片选
- `cs_high() -> None`
  - 拉高片选
- `transfer_byte(data: int) -> int`
  - 发送并接收一个字节
- `transfer(data: list[int]) -> list[int]`
  - 连续发送并接收多个字节
- `close() -> None`
  - 释放 GPIO line 和 chip 资源

### 参数说明

- `sclk` / `mosi` / `miso` / `cs` 都使用 `(chip, line)` 格式
- 4 根线可以在同一个 `gpiochip`，也可以分散在不同 `gpiochip`

## MAX31865

### 类定义

```python
class MAX31865:
    def __init__(
        self,
        spi,
        rref: float = MAX31865_DEFAULT_RREF,
        r0: float = MAX31865_DEFAULT_R0,
        wires: int = MAX31865_DEFAULT_WIRES,
        filter_frequency: int = MAX31865_DEFAULT_FILTER_FREQUENCY,
    )
```

### 类级转换接口

- `MAX31865.convert_adc_to_resistance(raw_adc: int, rref: float = 430.0) -> float`
- `MAX31865.convert_resistance_to_temperature(resistance: float, r0: float = 100.0) -> float`
- `MAX31865.convert_adc_to_temperature(raw_adc: int, rref: float = 430.0, r0: float = 100.0) -> float`

### 实例属性

- `raw_rtd: int`
  - 当前 RTD 原始 ADC 值
- `resistance: float`
  - 当前 RTD 电阻值
- `temperature: float`
  - 当前温度，单位摄氏度
- `fault_status: int`
  - 当前故障状态寄存器值

### 实例方法

- `read_fault() -> int`
- `clear_faults() -> None`
- `read_register(reg_addr: int) -> int`
- `read_registers(reg_addr: int, length: int) -> list[int]`
- `write_register(reg_addr: int, value: int) -> None`
- `write_registers(reg_addr: int, values: list[int]) -> None`
- `adc_to_resistance(raw_adc: int) -> float`
- `resistance_to_temperature(resistance: float) -> float`
- `calculate_temperature(raw_adc: int) -> float`
- `close() -> None`

## PeriPump

### 类定义

```python
class PeriPump:
    def __init__(
        self,
        tca9555_instance: TCA9555,
        pul_chip=PUL_CHIP,
        pul_line=PUL_LINE,
        dir_pin=DIR_PIN,
        ena_pin=ENA_PIN,
    )
```

### 依赖说明

- `PUL` 脉冲线通过 `gpiod` 直接控制
- `DIR` 和 `ENA` 通过 `TCA9555` 控制
- 所以创建 `PeriPump` 前必须先有一个可用的 `TCA9555` 实例

### 公开接口

- `enable() -> None`
  - 使能电机
- `disable() -> None`
  - 关闭电机使能
- `pulse() -> None`
  - 发送一个脉冲周期
- `run(revolutions=None) -> None`
  - 按圈数运行
- `run_by_time(seconds=None) -> None`
  - 按时间运行
- `set_pin_config(pul_chip=None, pul_line=None, dir_pin=None, ena_pin=None) -> None`
  - 重新配置 PUL / DIR / ENA 引脚
- `cleanup() -> None`
  - 清理资源
- `subdivision(subdiv_value) -> None`
  - 设置细分
- `direction(direction) -> None`
  - 设置方向，`1` 为正转，`0` 为反转
- `rpm(rpm_value) -> None`
  - 设置转速
- `set_subdivision(subdiv_value) -> None`
- `set_direction(direction) -> None`
- `set_rpm(rpm_value) -> None`

## 使用建议

- 新代码优先使用 `with` 管理 `ADS1115`、`TCA9555`、`SoftSPI`、`MAX31865`
- `PeriPump` 当前更接近业务控制类，建议显式调用 `cleanup()`
- 如果后续继续工程化，建议优先修正 `PeriPump.py`、`MAX31865.py`、`SoftSPI.py` 中现有的中文注释编码问题
