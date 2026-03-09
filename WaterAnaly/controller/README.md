# Controller 库使用记录

本文档记录 `WaterAnaly/controller` 计划使用的第三方 Python 库。

## 目标 Python 环境

请使用以下解释器：

```powershell
E:\anaconda3\envs\rk3568\python.exe
```

## 库与安装命令

1. 电机控制库（motor）

```powershell
E:\anaconda3\envs\rk3568\python.exe -m pip install adafruit-circuitpython-motor
```

文档：<https://docs.circuitpython.org/projects/motor/en/latest/>

2. MAX31865 库

```powershell
E:\anaconda3\envs\rk3568\python.exe -m pip install adafruit-circuitpython-max31865
```

文档：<https://docs.circuitpython.org/projects/max31865/en/latest/>

3. ADS1115 库

```powershell
E:\anaconda3\envs\rk3568\python.exe -m pip install adafruit-circuitpython-ads1x15
```

文档：<https://docs.circuitpython.org/projects/ads1x15/en/stable/>

4. TCA9555 库

```powershell
E:\anaconda3\envs\rk3568\python.exe -m pip install community-circuitpython-tca9555
```

项目地址：<https://github.com/lesamouraipourpre/Community_CircuitPython_TCA9555>

## 临时测试脚本

已新增独立测试脚本（不会修改 `main.py`）：

- `src/cp_test.py`

脚本特点：

1. 用 CircuitPython 库替代 `controller/lib` 下的实现。
2. 复刻 `main.py` 的流程结构，并包含原先注释掉的推水/检测/排水流程。
3. 所有可改参数都放在脚本最上面的常量区。

运行：

```powershell
E:\anaconda3\envs\rk3568\python.exe .\WaterAnaly\controller\src\cp_test.py
```

使用方法：

1. 先改 `cp_test.py` 顶部常量（I2C 地址、引脚、流程开关）。
2. 再执行脚本进行整体验证。
