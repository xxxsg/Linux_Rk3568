# GPIO 使用说明（中文）

本 README 针对在 Linux（如树莓派或其他嵌入式 Linux）上使用 Python 操作 GPIO 的常见配置与问题排查进行说明，包含与 `libgpiod` Python 绑定相关的解决办法。

**前提**
- 运行环境为 Linux，内核支持 GPIO 子系统。
- 对目标 GPIO 设备有权限（通常需要 root 或在 `gpio` 组中）。

**目录**
- 安装依赖
- 运行示例
- 常见错误与解决（包括 `module 'gpiod' has no attribute 'Chip'`）
- 模拟模式说明
- API 接口说明

**安装依赖**
- 建议安装系统级的 libgpiod：

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt update
sudo apt install -y libgpiod2 libgpiod-dev python3-libgpiod
```

- 若使用 pip 安装 Python 绑定（可选）：

```bash
pip install gpiod
# 或者
pip install libgpiod
```

注：不同发行版包名可能不同，优先使用系统包管理器安装 `libgpiod`，再安装 Python 绑定以保证 ABI 兼容性。

**运行示例**
项目里有一个简单的 Flask 示例服务，主文件为 `app.py`。

1. 安装 Flask 和相关依赖

```bash
pip install flask
# 如果硬件支持，还需要安装GPIO库
pip install gpiod
```

或者使用requirements.txt安装所有依赖：
```bash
pip install -r requirements.txt
```

2. 设置环境变量（可选，默认已在代码中设定）

```bash
export GPIO_CHIP=gpiochip0
export GPIO_LINE=17
```

也可以通过 .env 文件进行配置：

```bash
# .env
GPIO_CHIP=gpiochip0
GPIO_LINE=17
FLASK_ENV=production
HOST=0.0.0.0
PORT=5000
```

3. 运行服务（可能需要 root 权限以访问 GPIO）：

```bash
# 普通运行（若有权限）
python3 app.py
# 如果需要 root
sudo python3 app.py
```

打开浏览器访问 `http://<你的机器IP>:5000` 查看控制界面。

**API 接口说明**
- `GET /` - 获取主页，显示LED控制界面
- `GET /status` - 获取当前LED状态 (返回JSON格式)
- `POST /on` - 打开LED (支持JSON响应)
- `POST /off` - 关闭LED (支持JSON响应)
- `POST /toggle` - 切换LED状态 (支持JSON响应)

**关于错误：module 'gpiod' has no attribute 'Chip'**
如果你在启动时报错：

```
AttributeError: module 'gpiod' has no attribute 'Chip'
```

可能原因与解决办法：
- 原因：系统中安装的 `gpiod` Python 模块版本与代码期望的 `libgpiod` 绑定不匹配，或仅安装了名称相同但接口不同的包。
- 解决：
  - 首先通过系统包管理器安装 `libgpiod`（见上）并安装对应的 Python 绑定 `python3-libgpiod` 或 `gpiod`。
  - 确认 Python 中加载的模块位置：

```bash
python3 -c "import gpiod, inspect; print(gpiod, inspect.getfile(gpiod))"
```

  - 如果模块路径不是系统 `site-packages` 或看起来不对（例如来自旧项目目录），请卸载冲突的包：

```bash
pip uninstall gpiod libgpiod
sudo apt remove python3-gpiod # 视发行版而定
```

然后重新安装正确的绑定。

**本项目的兼容策略**
- 为提高健壮性，`app.py` 已加入检测：当 Python 环境不包含兼容的 `gpiod.Chip` 接口时，程序会自动进入"模拟模式"（不会访问真实硬件），并在启动时打印警告与安装提示，方便在开发机调试。
- 新增了详细的日志记录功能，便于调试问题。
- 支持同时处理HTML表单提交和JSON API请求。

**权限与运行注意事项**
- 访问 `/dev/gpiochip*` 需要相应权限。可以通过以下方式授予非 root 权限：
  - 将运行用户加入 `gpio` 组（如果系统有该组）：

```bash
sudo usermod -aG gpio $USER
# 之后重新登录会话
```

  - 或者使用 `sudo` 运行程序（不推荐长期使用）。

**测试硬件 GPIO（简单）**
- 使用 `gpiod` 工具查看可用芯片与线：

```bash
# 列出芯片
gpiodetect
# 列出芯片上的线
gpioinfo gpiochip0
```

- 在确认芯片名与线号后，设置 `GPIO_CHIP` 与 `GPIO_LINE` 环境变量，再运行 `app.py`。

**如果你仍然遇到问题**
- 请把以下信息贴出来：
  - `python3 -V`
  - `pip show gpiod`（如果已安装）
  - `gpiodetect` 与 `gpioinfo gpiochip0` 的输出
  - 启动时报错的完整 trace

这样我可以更精确地帮你定位问题。

---

README 编写完毕