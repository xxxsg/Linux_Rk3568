from flask import Flask, render_template, redirect, url_for, jsonify, request
import os
import logging
import atexit

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import gpiod
except ImportError:
    gpiod = None
    logger.warning("python-gpiod 未安装，将使用模拟模式")

# 配置使用 gpiocmayhip1，line 0 控制第一个 LED，line 1 控制第二个 LED
GPIO_CHIP = os.getenv("GPIO_CHIP", "gpiochip1")
LED1_LINE = int(os.getenv("LED1_LINE", "0"))  # 第一个 LED 连接的引脚
LED2_LINE = int(os.getenv("LED2_LINE", "1"))  # 第二个 LED 连接的引脚

class GPIOController:
    """GPIO控制器类，管理两个LED开关操作"""
    
    def __init__(self, chip_name, led1_line, led2_line):
        self.chip_name = chip_name
        self.led1_line = led1_line
        self.led2_line = led2_line
        self._setup_gpio()
    
    def _setup_gpio(self):
        """初始化GPIO设置"""
        self.sim_mode = not gpiod or not hasattr(gpiod, "Chip")
        
        if self.sim_mode:
            self._init_sim_mode()
        else:
            self._init_hardware_mode()
    
    def _init_sim_mode(self):
        """初始化模拟模式"""
        self.led1_state = 0
        self.led2_state = 0
        if gpiod is None:
            logger.warning("python gpiod 未安装，已进入模拟 GPIO 模式。请参考 README 安装 libgpiod 绑定。")
        else:
            logger.warning("sudo python3 app.py。")
    
    def _init_hardware_mode(self):
        """初始化硬件GPIO模式"""
        try:
            # 使用完整的设备路径，参照 gpio_test.py
            chip_path = f"/dev/{self.chip_name}"
            self.chip = gpiod.Chip(chip_path)
            logger.info(f"成功访问GPIO芯片: {chip_path}")
            
            # 初始化第一个 LED 引脚
            self.led1_line_obj = self.chip.get_line(self.led1_line)
            logger.info(f"正在请求GPIO线路 {self.led1_line} 用于 LED1...")
            if not self._request_led_line(self.led1_line_obj, "led1"):
                raise Exception(f"无法请求GPIO线路 {self.led1_line}")
                
            # 初始化第二个 LED 引脚
            self.led2_line_obj = self.chip.get_line(self.led2_line)
            logger.info(f"正在请求GPIO线路 {self.led2_line} 用于 LED2...")
            if not self._request_led_line(self.led2_line_obj, "led2"):
                raise Exception(f"无法请求GPIO线路 {self.led2_line}")
            
            logger.info(f"GPIO LED1 {self.led1_line} 和 LED2 {self.led2_line} 初始化成功")
                
        except Exception as e:
            logger.error(f"GPIO芯片初始化失败: {e}")
            logger.warning("将退回为模拟模式。请检查GPIO权限和libgpiod安装。")
            self._fallback_to_sim_mode()
    
    def _request_led_line(self, line_obj, name):
        """请求 LED 引脚（输出）- 使用正确的 gpiod v1.x API"""
        try:
            # 使用 gpio_test.py 中的正确写法
            line_obj.request(
                consumer=f"flask-{name}",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[0]  # 初始值为低电平
            )
            logger.info(f"GPIO线路 {line_obj.offset()} ({name}) 请求成功")
            return True
        except Exception as e:
            logger.error(f"GPIO线路请求失败: {e}")
            return False
    
    def _fallback_to_sim_mode(self):
        """回退到模拟模式"""
        logger.warning("GPIO初始化失败，切换到模拟模式")
        self.sim_mode = True
        self.led1_state = 0
        self.led2_state = 0
        self.led1_line_obj = None
        self.led2_line_obj = None
    
    def set_led1(self, value: int):
        """设置第一个LED状态"""
        value = 1 if value else 0
        
        logger.info(f"正在设置 {self.chip_name} 上的线路 {self.led1_line} (LED1) 为 {'HIGH' if value else 'LOW'}")
        
        if self.sim_mode:
            self.led1_state = value
            logger.debug(f"模拟模式 - 设置LED1状态: {value}")
        else:
            try:
                self.led1_line_obj.set_value(value)
                logger.info(f"硬件模式 - 成功设置 {self.chip_name}:{self.led1_line} (LED1) 为 {'HIGH' if value else 'LOW'}")
                self.led1_state = value
            except Exception as e:
                logger.error(f"设置LED1 GPIO值失败: {e}")
    
    def set_led2(self, value: int):
        """设置第二个LED状态"""
        value = 1 if value else 0
        
        logger.info(f"正在设置 {self.chip_name} 上的线路 {self.led2_line} (LED2) 为 {'HIGH' if value else 'LOW'}")
        
        if self.sim_mode:
            self.led2_state = value
            logger.debug(f"模拟模式 - 设置LED2状态: {value}")
        else:
            try:
                self.led2_line_obj.set_value(value)
                logger.info(f"硬件模式 - 成功设置 {self.chip_name}:{self.led2_line} (LED2) 为 {'HIGH' if value else 'LOW'}")
                self.led2_state = value
            except Exception as e:
                logger.error(f"设置LED2 GPIO值失败: {e}")
    
    def get_led1(self) -> int:
        """获取第一个LED状态"""
        if self.sim_mode:
            return self.led1_state
        else:
            try:
                value = self.led1_line_obj.get_value()
                logger.debug(f"硬件模式 - 获取 {self.chip_name}:{self.led1_line} (LED1) 值: {value}")
                return value
            except Exception as e:
                logger.error(f"读取LED1 GPIO值失败: {e}")
                return self.led1_state  # 返回缓存的状态
    
    def get_led2(self) -> int:
        """获取第二个LED状态"""
        if self.sim_mode:
            return self.led2_state
        else:
            try:
                value = self.led2_line_obj.get_value()
                logger.debug(f"硬件模式 - 获取 {self.chip_name}:{self.led2_line} (LED2) 值: {value}")
                return value
            except Exception as e:
                logger.error(f"读取LED2 GPIO值失败: {e}")
                return self.led2_state  # 返回缓存的状态
    
    def toggle_led1(self):
        """切换第一个LED状态"""
        current = self.get_led1()
        new_state = 1 - current
        logger.info(f"切换 LED1 状态从 {'ON' if current else 'OFF'} 到 {'ON' if new_state else 'OFF'}")
        self.set_led1(new_state)
        return new_state

    def toggle_led2(self):
        """切换第二个LED状态"""
        current = self.get_led2()
        new_state = 1 - current
        logger.info(f"切换 LED2 状态从 {'ON' if current else 'OFF'} 到 {'ON' if new_state else 'OFF'}")
        self.set_led2(new_state)
        return new_state
    
    def cleanup(self):
        """清理GPIO资源"""
        if not self.sim_mode and hasattr(self, 'chip'):
            try:
                if hasattr(self, 'led1_line_obj') and self.led1_line_obj:
                    self.led1_line_obj.release()
                if hasattr(self, 'led2_line_obj') and self.led2_line_obj:
                    self.led2_line_obj.release()
                self.chip.close()
                logger.info("GPIO资源已清理")
            except Exception as e:
                logger.error(f"清理GPIO资源时出错: {e}")

# 创建应用实例
app = Flask(__name__)
gpio = GPIOController(GPIO_CHIP, LED1_LINE, LED2_LINE)

@app.route("/", methods=["GET"])
def index():
    """主页 - 显示两个LED状态"""
    led1_state = gpio.get_led1()
    led2_state = gpio.get_led2()
    logger.info(f"显示主页 - LED1: {'ON' if led1_state else 'OFF'}, LED2: {'ON' if led2_state else 'OFF'}")
    return render_template("index.html", led1_state=led1_state, led2_state=led2_state)

@app.route("/toggle1", methods=["POST"])
def toggle_led1():
    """切换第一个LED状态的API端点"""
    logger.info("收到切换 LED1 状态的请求")
    new_state = gpio.toggle_led1()
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({"status": "success", "led1_state": new_state})
    else:
        logger.info("重定向到主页...")
        return redirect(url_for("index"))

@app.route("/toggle2", methods=["POST"])
def toggle_led2():
    """切换第二个LED状态的API端点"""
    logger.info("收到切换 LED2 状态的请求")
    new_state = gpio.toggle_led2()
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({"status": "success", "led2_state": new_state})
    else:
        logger.info("重定向到主页...")
        return redirect(url_for("index"))

@app.route("/on1", methods=["POST"])
def turn_on1():
    """打开第一个LED"""
    logger.info("收到打开 LED1 的请求")
    gpio.set_led1(1)
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({"status": "success", "action": "turn_on1", "led1_state": 1})
    else:
        logger.info("重定向到主页...")
        return redirect(url_for("index"))

@app.route("/off1", methods=["POST"])
def turn_off1():
    """关闭第一个LED"""
    logger.info("收到关闭 LED1 的请求")
    gpio.set_led1(0)
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({"status": "success", "action": "turn_off1", "led1_state": 0})
    else:
        logger.info("重定向到主页...")
        return redirect(url_for("index"))

@app.route("/on2", methods=["POST"])
def turn_on2():
    """打开第二个LED"""
    logger.info("收到打开 LED2 的请求")
    gpio.set_led2(1)
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({"status": "success", "action": "turn_on2", "led2_state": 1})
    else:
        logger.info("重定向到主页...")
        return redirect(url_for("index"))

@app.route("/off2", methods=["POST"])
def turn_off2():
    """关闭第二个LED"""
    logger.info("收到关闭 LED2 的请求")
    gpio.set_led2(0)
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({"status": "success", "action": "turn_off2", "led2_state": 0})
    else:
        logger.info("重定向到主页...")
        return redirect(url_for("index"))

@app.route("/status", methods=["GET"])
def get_status():
    """获取当前两个LED状态"""
    led1_state = gpio.get_led1()
    led2_state = gpio.get_led2()
    logger.info(f"返回状态 - LED1: {'ON' if led1_state else 'OFF'}, LED2: {'ON' if led2_state else 'OFF'}")
    return jsonify({
        "status": "success", 
        "led1_state": led1_state,
        "led2_state": led2_state
    })

if __name__ == "__main__":
    # 注册清理函数
    atexit.register(gpio.cleanup)
    
    logger.info("启动Flask应用 - http://0.0.0.0:5000")
    logger.info(f"使用GPIO芯片: {GPIO_CHIP}, LED1引脚: {LED1_LINE}, LED2引脚: {LED2_LINE}")
    app.run(host="0.0.0.0", port=5000, debug=False)