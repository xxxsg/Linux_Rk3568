# 水分析流程伪代码重写说明

本文不是实现代码，而是基于当前仓库 `WaterAnaly/controller/lib` 的实际接口，对原始伪代码做一次更贴近工程落地的重写。

目标：

- 伪代码中的对象、函数名尽量对应现有库能力
- 分层清晰，方便后续拆成多个 `.py` 文件
- 重点描述“怎么组织流程”，而不是写死某一种实现

---

## 1. 建议的工程分层

建议按下面方式组织：

- `config.py`
  - 管理引脚映射、阈值、超时、工艺参数
- `hardware.py`
  - 负责初始化 `ADS1115`、`TCA9555`、`Stepper`、`Pump`、`MAX31865`
  - 对底层设备做轻量包装
- `primitives.py`
  - 基础动作：开关阀、吸液、排液、等待满位/空位、读取温度、读取吸光度
- `recipe.py`
  - 工艺步骤：清洗、加样、加试剂、加热、静置、搅拌、读数、收尾
- `main.py`
  - 主入口，负责串起整套流程

---

## 2. 当前仓库里可直接复用的底层能力

### 2.1 阀控制

已有库：

- `lib.TCA9555.TCA9555`
- `lib.pins.Tca9555Pin`

建议封装：

```python
class ValveController:
    def open(names: str | list[str]) -> None
    def close(names: str | list[str]) -> None
    def close_all() -> None
```

语义：

- `open(["sample", "dissolver"])` 表示打开若干阀
- `close_all()` 表示所有阀复位到安全状态

---

### 2.2 蠕动泵 / 步进驱动

已有库：

- `lib.stepper.Stepper`
- `lib.pump.Pump`

建议使用方式：

```python
stepper = Stepper(
    pul_pin=...,
    dir_pin=...,
    ena_pin=...,
    steps_per_rev=800,
)
stepper.configure_driver(
    dir_high_forward=True,
    ena_low_enable=True,
    auto_enable=True,
)
stepper.set_rpm(300)

pump = Pump(driver=stepper, aspirate_direction="reverse")
```

在流程层只关心：

```python
pump.aspirate_continuous()
pump.dispense_continuous()
pump.aspirate_time(seconds)
pump.dispense_time(seconds)
pump.stop()
pump.emergency_stop()
```

---

### 2.3 光学检测

已有库：

- `lib.ADS1115.ADS1115`

建议约定通道：

- `channel 0`: 计量上光学
- `channel 1`: 计量下光学
- `channel 2`: 消解吸光度

建议封装：

```python
class MeterOptics:
    def read_upper_mv() -> float
    def read_lower_mv() -> float

class DigestOptics:
    def read_absorbance_mv() -> float
```

---

### 2.4 温度检测

已有库：

- `lib.MAX31865.MAX31865`
- `lib.SoftSPI.SoftSPI`

建议封装：

```python
class TemperatureSensor:
    def read_temperature_c() -> float
```

说明：

- 当前库里有温度采集能力
- 如果后续还有加热执行器，需要再补一个 `HeaterController`

---

## 3. 配置层伪代码

```python
# 方向定义
DIR_FORWARD = "FORWARD"
DIR_REVERSE = "REVERSE"

# 采样稳定判断
STABLE_SAMPLE_PERIOD_MS = 20
STABLE_SAMPLE_COUNT = 10

# 阀切换稳定时间
VALVE_SETTLE_MS = 50

# 超时
TAKE_LARGE_TIMEOUT_MS = 15000
TAKE_SMALL_TIMEOUT_MS = 15000
DISPENSE_TIMEOUT_MS = 10000
PULL_DIGESTOR_TIMEOUT_MS = 12000
HEAT_UP_TIMEOUT_MS = 180000

# 工艺时序
SUPPLEMENT_BLOW_MS = 500
HEAT_HOLD_MS = 300000
DIGEST_SETTLE_TOTAL_MS = 900000
STIR_DURATION_MS = 15000
OPTICS_WARMUP_MS = 2000
CLEAN_PAUSE_MS = 20000

# 判定阈值
UPPER_FULL_THRESHOLD_MV = ...
LOWER_FULL_THRESHOLD_MV = ...
EMPTY_THRESHOLD_MV = ...

# 阀位映射
VALVE_PIN_MAP = {
    "dissolver": ...,
    "std_1": ...,
    "std_2": ...,
    "sample": ...,
    "analysis_waste": ...,
    "reagent_a": ...,
    "reagent_b": ...,
    "reagent_c": ...,
    "clean_waste": ...,
    "dissolver_up": ...,
    "dissolver_down": ...,
}
```

---

## 4. 硬件装配层伪代码

```python
def build_hardware():
    tca = TCA9555(i2c_bus=1, addr=0x20)

    ads = ADS1115(i2c_bus=1, addr=0x48)
    ads.set_gain(ADS1115_REG_CONFIG_PGA_4_096V)

    valve_pins = {
        name: Tca9555Pin(tca, pin_no, initial_value=False)
        for name, pin_no in VALVE_PIN_MAP.items()
    }
    valve = ValveController(valve_pins)

    pul_pin = GpiodPin(...)
    dir_pin = Tca9555Pin(tca, ...)
    ena_pin = Tca9555Pin(tca, ..., initial_value=True)

    stepper = Stepper(
        pul_pin=pul_pin,
        dir_pin=dir_pin,
        ena_pin=ena_pin,
        steps_per_rev=800,
    )
    stepper.configure_driver(
        dir_high_forward=True,
        ena_low_enable=True,
        auto_enable=True,
    )
    stepper.set_rpm(300)
    pump = Pump(driver=stepper, aspirate_direction="reverse")

    spi = SoftSPI(...)
    max31865 = MAX31865(spi=spi, rref=430.0, r0=100.0, wires=2, filter_frequency=50)

    meter_optics = MeterOptics(ads)
    digest_optics = DigestOptics(ads)
    temp_sensor = TemperatureSensor(max31865)

    return HardwareContext(
        valve=valve,
        pump=pump,
        meter_optics=meter_optics,
        digest_optics=digest_optics,
        temp_sensor=temp_sensor,
        raw_devices=[tca, ads, spi, max31865, stepper],
    )
```

---

## 5. 基础工具函数伪代码

```python
def sleep_ms(ms):
    ...

def wait_until(cond_fn, timeout_ms, poll_ms=50) -> bool:
    ...

def stable_truth(cond_fn) -> bool:
    repeat STABLE_SAMPLE_COUNT times:
        if not cond_fn():
            return False
        sleep_ms(STABLE_SAMPLE_PERIOD_MS)
    return True
```

---

## 6. 状态判断伪代码

```python
def is_meter_full(meter_optics, volume: str) -> bool:
    if volume == "large":
        return stable_truth(
            lambda: meter_optics.read_upper_mv() <= UPPER_FULL_THRESHOLD_MV
        )
    if volume == "small":
        return stable_truth(
            lambda: meter_optics.read_lower_mv() <= LOWER_FULL_THRESHOLD_MV
        )
    raise ValueError("unsupported volume")


def is_meter_empty(meter_optics) -> bool:
    return stable_truth(
        lambda: meter_optics.read_upper_mv() >= EMPTY_THRESHOLD_MV
    )
```

---

## 7. 路由动作伪代码

### 7.1 源液 -> 计量单元

```python
def route_source_to_meter(valve, source_name: str):
    valve.close_all()
    valve.open([source_name, "dissolver"])
    sleep_ms(VALVE_SETTLE_MS)
```

说明：

- `dissolver` 在这里代表计量单元入口阀的角色
- 如果实际命名不同，应统一成更清晰的业务名，比如 `meter_inlet`

### 7.2 计量单元 -> 目标位置

```python
def route_meter_to_target(valve, targets: list[str]):
    valve.close_all()
    valve.open(targets)
    sleep_ms(VALVE_SETTLE_MS)
```

---

## 8. 基础动作伪代码

### 8.1 吸液

```python
def aspirate(ctx, source_name: str, volume: str):
    timeout_ms = TAKE_LARGE_TIMEOUT_MS if volume == "large" else TAKE_SMALL_TIMEOUT_MS

    route_source_to_meter(ctx.valve, source_name)

    start_pump_in_background(ctx.pump.aspirate_continuous)
    ok = wait_until(
        lambda: is_meter_full(ctx.meter_optics, volume),
        timeout_ms,
        poll_ms=50,
    )
    ctx.pump.stop()
    ctx.valve.close_all()

    if not ok:
        raise RecipeError("aspirate timeout")
```

说明：

- 这里一定要考虑 `Pump.aspirate_continuous()` 是阻塞式调用
- 真正实现时通常需要后台线程或异步任务

### 8.2 排液

```python
def dispense(ctx, targets: list[str]):
    route_meter_to_target(ctx.valve, targets)

    start_pump_in_background(ctx.pump.dispense_continuous)
    ok = wait_until(
        lambda: is_meter_empty(ctx.meter_optics),
        DISPENSE_TIMEOUT_MS,
        poll_ms=50,
    )
    ctx.pump.stop()

    if not ok:
        ctx.valve.close_all()
        raise RecipeError("dispense timeout")

    # 补吹，尽量排净
    ctx.pump.dispense_time(SUPPLEMENT_BLOW_MS / 1000.0)
    ctx.valve.close_all()
```

### 8.3 加液到消解器

```python
def add_to_digestor(ctx, source_name: str, volume: str):
    aspirate(ctx, source_name, volume)
    dispense(ctx, ["dissolver_up", "dissolver_down"])
```

### 8.4 润洗到废液

```python
def rinse_to_waste(ctx, source_name: str, waste_name: str):
    aspirate(ctx, source_name, "small")
    dispense(ctx, [waste_name])
```

### 8.5 管路冲洗

```python
def flush_pipeline(ctx, source_name: str, waste_name: str, times: int, volume: str):
    repeat times:
        aspirate(ctx, source_name, volume)
        dispense(ctx, [waste_name])
        sleep_ms(200)
```

### 8.6 从消解器抽回计量单元

```python
def pull_digestor_to_meter(ctx):
    ctx.valve.close_all()
    ctx.valve.open(["dissolver_up", "dissolver_down", "dissolver"])
    sleep_ms(VALVE_SETTLE_MS)

    start_pump_in_background(ctx.pump.aspirate_continuous)
    ok = wait_until(
        lambda: is_meter_full(ctx.meter_optics, "large"),
        PULL_DIGESTOR_TIMEOUT_MS,
        poll_ms=50,
    )
    ctx.pump.stop()
    ctx.valve.close_all()

    if not ok:
        raise RecipeError("pull digestor timeout")
```

### 8.7 排空消解器

```python
def empty_digestor(ctx, waste_name: str):
    pull_digestor_to_meter(ctx)
    dispense(ctx, [waste_name])
```

### 8.8 通气搅拌

```python
def aerate_digestor(ctx, duration_ms: int):
    ctx.valve.close_all()
    ctx.valve.open(["dissolver_up", "dissolver_down"])
    sleep_ms(VALVE_SETTLE_MS)

    ctx.pump.dispense_time(duration_ms / 1000.0)
    ctx.valve.close_all()
```

### 8.9 温度等待

```python
def heat_and_hold(ctx, target_temp_c: float, hold_ms: int):
    ok = wait_until(
        lambda: ctx.temp_sensor.read_temperature_c() >= target_temp_c,
        HEAT_UP_TIMEOUT_MS,
        poll_ms=500,
    )
    if not ok:
        raise RecipeError("heat timeout")

    sleep_ms(hold_ms)
```

说明：

- 这里只体现“等温度到位并保持”
- 如果后续存在真实加热控制，应单独增加 `heater.start()` / `heater.stop()`

### 8.10 读取消解吸光度

```python
def read_digest_value(ctx) -> float:
    sleep_ms(OPTICS_WARMUP_MS)
    return ctx.digest_optics.read_absorbance_mv()
```

---

## 9. 工艺流程伪代码

### 9.1 开机清洗

```python
def clean_system(ctx):
    add_to_digestor(ctx, "std_1", "large")
    sleep_ms(CLEAN_PAUSE_MS)
    empty_digestor(ctx, "analysis_waste")
    flush_pipeline(ctx, "std_1", "analysis_waste", times=3, volume="large")
```

### 9.2 主流程

```python
def run_water_analysis(ctx, standard_concentration: float):
    ctx.valve.close_all()

    # 0) 开机清洗
    clean_system(ctx)

    # 1) 样品：润洗 + 正式加样
    rinse_to_waste(ctx, "sample", "analysis_waste")
    add_to_digestor(ctx, "sample", "large")

    # 2) 标液：润洗 + 加入
    rinse_to_waste(ctx, "std_2", "analysis_waste")
    add_to_digestor(ctx, "std_2", "large")

    # 3) 试剂A：润洗 + 加入 + 标一冲洗
    rinse_to_waste(ctx, "reagent_a", "analysis_waste")
    add_to_digestor(ctx, "reagent_a", "large")
    flush_pipeline(ctx, "std_1", "analysis_waste", times=2, volume="large")

    # 4) 加热并恒温
    heat_and_hold(ctx, target_temp_c=50.0, hold_ms=HEAT_HOLD_MS)

    # 5) 试剂B：润洗 + 加入 + 标一冲洗
    rinse_to_waste(ctx, "reagent_b", "analysis_waste")
    add_to_digestor(ctx, "reagent_b", "large")
    flush_pipeline(ctx, "std_1", "analysis_waste", times=1, volume="large")

    # 6) 静置，中途通气搅拌
    sleep_ms(DIGEST_SETTLE_TOTAL_MS / 2)
    aerate_digestor(ctx, STIR_DURATION_MS)
    sleep_ms(DIGEST_SETTLE_TOTAL_MS / 2)

    # 7) 试剂C：润洗 + 加入 + 标一冲洗
    rinse_to_waste(ctx, "reagent_c", "analysis_waste")
    add_to_digestor(ctx, "reagent_c", "large")
    flush_pipeline(ctx, "std_1", "analysis_waste", times=2, volume="large")

    # 8) 读数
    absorbance = read_digest_value(ctx)

    # 9) 浓度换算
    concentration = compute_concentration(absorbance, standard_concentration)

    # 10) 收尾
    empty_digestor(ctx, "analysis_waste")
    clean_system(ctx)
    ctx.valve.close_all()

    return {
        "absorbance": absorbance,
        "concentration": concentration,
    }
```

---

## 10. 浓度换算接口建议

实际算法应单独抽离，不要写死在主流程中。

```python
def compute_concentration(absorbance: float, standard_concentration: float) -> float:
    # 占位
    return ...
```

建议后续根据标液、校准曲线、空白值做成独立模块，例如：

- `calibration.py`
- `compute_concentration()`
- `apply_blank_correction()`
- `fit_standard_curve()`

---

## 11. 异常与安全建议

所有流程动作都建议遵守下面规则：

- 任何异常时先 `pump.stop()` 或 `pump.emergency_stop()`
- 然后 `valve.close_all()`
- 最后关闭底层设备句柄

统一形式：

```python
try:
    run_water_analysis(ctx, standard_concentration=1.0)
finally:
    safe_shutdown(ctx)
```

---

## 12. 总结

这版重写后的伪代码，相比原文更贴近你仓库现状，主要特点是：

- 不再抽象出脱离仓库的新接口
- 直接围绕 `controller/lib` 现有类设计
- 明确区分“硬件装配”和“工艺流程”
- 适合后续稳定拆成多个 `.py` 文件
- 保留了主流工程里的配置、上下文、原语、配方四层结构

如果后面你需要，我可以继续只改这份文档，把它再整理成：

- “更偏产品说明”的版本
- “更偏开发设计文档”的版本
- “直接给团队评审”的版本
