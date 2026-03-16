"""步进驱动层。"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from lib.pins import OutputPin


class Stepper(object):
    """PUL / DIR / ENA 型步进驱动器。

    设计原则：
    - `__init__` 只保留必要参数
    - 常用运行参数放到对象属性里，方便后续直接修改
    - 电平极性只在这里处理，上层不用关心接线高低有效
    """

    def __init__(
        self,
        pul_pin: OutputPin,
        dir_pin: OutputPin,
        ena_pin: Optional[OutputPin] = None,
        steps_per_rev: int = 800,
        dir_high_forward: bool = True,
        ena_low_enable: bool = True,
        auto_enable: bool = True,
    ) -> None:
        """初始化步进驱动器。

        参数：
            pul_pin: 脉冲输出脚，接驱动器 PUL
            dir_pin: 方向输出脚，接驱动器 DIR
            ena_pin: 使能输出脚，接驱动器 ENA，可选
            steps_per_rev: 当前每转步数，默认 800
            dir_high_forward: DIR 高电平是否表示正转
            ena_low_enable: ENA 低电平是否表示使能
            auto_enable: 运动前自动使能，运动后自动失能
        """
        if pul_pin is None or dir_pin is None:
            raise ValueError("pul_pin 和 dir_pin 不能为空")

        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin

        # 下面这些参数都可以在初始化后直接改，比如：
        # stepper.rpm = 200
        # stepper.default_revs = 2
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")
        self.rpm = 300.0
        self.default_revs = 10.0
        self.default_seconds = 3.0
        self.pulse_high_s = None
        self.pulse_low_s = None

        self.dir_high_forward = bool(dir_high_forward)
        self.ena_low_enable = bool(ena_low_enable)
        self.auto_enable = bool(auto_enable)
        self.forward = True

        self._stop = False
        self._estop = False
        self._enabled = False

        self.disable()

    def _check_pos_number(self, value, name: str) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError("%s 必须是数字" % name)
        if value <= 0:
            raise ValueError("%s 必须大于 0" % name)
        return float(value)

    def _check_pos_int(self, value, name: str) -> int:
        if not isinstance(value, int):
            raise TypeError("%s 必须是整数" % name)
        if value <= 0:
            raise ValueError("%s 必须大于 0" % name)
        return value

    def _check_nonneg_int(self, value, name: str) -> int:
        if not isinstance(value, int):
            raise TypeError("%s 必须是整数" % name)
        if value < 0:
            raise ValueError("%s 不能小于 0" % name)
        return value

    def _pulse_times(self) -> Tuple[float, float]:
        """计算一个脉冲的高低电平时间。"""
        if self.pulse_high_s is not None or self.pulse_low_s is not None:
            high_s = self.pulse_high_s
            low_s = self.pulse_low_s

            if high_s is None:
                high_s = self._check_pos_number(low_s, "pulse_low_s")
            if low_s is None:
                low_s = self._check_pos_number(high_s, "pulse_high_s")
            return float(high_s), float(low_s)

        rpm = self._check_pos_number(self.rpm, "rpm")
        steps_per_rev = self._check_pos_int(self.steps_per_rev, "steps_per_rev")
        period = 60.0 / (rpm * steps_per_rev)
        return period / 2.0, period / 2.0

    def _set_dir_pin(self, forward: bool) -> None:
        if self.dir_high_forward:
            self.dir_pin.write(forward)
        else:
            self.dir_pin.write(not forward)
        self.forward = bool(forward)

    def _set_ena_pin(self, enabled: bool) -> None:
        if self.ena_pin is None:
            self._enabled = enabled
            return

        if self.ena_low_enable:
            self.ena_pin.write(not enabled)
        else:
            self.ena_pin.write(enabled)
        self._enabled = enabled

    def _start(self, direction: Optional[bool]) -> None:
        self._stop = False
        self._estop = False
        if direction is not None:
            self.set_direction(direction)
        if self.auto_enable:
            self.enable()

    def _finish(self) -> None:
        if self.auto_enable:
            self.disable()

    def _should_stop(self) -> bool:
        return self._stop or self._estop

    def enable(self) -> None:
        """使能驱动器。"""
        self._set_ena_pin(True)

    def disable(self) -> None:
        """失能驱动器。"""
        self._set_ena_pin(False)

    def set_direction(self, forward: bool) -> None:
        """设置方向。

        参数：
            forward: True 表示正转，False 表示反转
        """
        if not isinstance(forward, bool):
            raise TypeError("forward 必须是 bool")
        self._set_dir_pin(forward)

    def set_rpm(self, rpm: float) -> None:
        """设置转速。"""
        self.rpm = self._check_pos_number(rpm, "rpm")

    def set_steps_per_rev(self, steps_per_rev: int) -> None:
        """设置每转步数。"""
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")

    def set_subdivision(self, subdivision: int) -> None:
        """兼容旧命名，等同于设置每转步数。"""
        self.set_steps_per_rev(subdivision)

    def set_default_revs(self, revs: float) -> None:
        """设置默认圈数。"""
        self.default_revs = self._check_pos_number(revs, "default_revs")

    def set_default_seconds(self, seconds: float) -> None:
        """设置默认运行时间。"""
        self.default_seconds = self._check_pos_number(seconds, "default_seconds")

    def pulse_once(self) -> None:
        """输出一个完整脉冲。"""
        high_s, low_s = self._pulse_times()
        self.pul_pin.high()
        time.sleep(high_s)
        self.pul_pin.low()
        time.sleep(low_s)

    def move_steps(self, steps: int, direction: Optional[bool] = None) -> None:
        """按步数运行。

        参数：
            steps: 运行步数
            direction: 可选，临时指定方向
        """
        total_steps = self._check_nonneg_int(steps, "steps")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction 必须是 bool 或 None")

        self._start(direction)
        try:
            index = 0
            while index < total_steps:
                if self._should_stop():
                    break
                self.pulse_once()
                index += 1
        finally:
            self._finish()

    def move_revolutions(self, revolutions: Optional[float] = None, direction: Optional[bool] = None) -> None:
        """按圈数运行。"""
        if revolutions is None:
            revolutions = self.default_revs
        revs = self._check_pos_number(revolutions, "revolutions")
        steps = int(round(revs * self._check_pos_int(self.steps_per_rev, "steps_per_rev")))
        self.move_steps(steps, direction=direction)

    def run_for_time(self, seconds: Optional[float] = None, direction: Optional[bool] = None) -> None:
        """按时间运行。"""
        if seconds is None:
            seconds = self.default_seconds
        duration = self._check_pos_number(seconds, "seconds")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction 必须是 bool 或 None")

        self._start(direction)
        deadline = time.time() + duration
        try:
            while time.time() < deadline:
                if self._should_stop():
                    break
                self.pulse_once()
        finally:
            self._finish()

    def run_continuous(self, direction: Optional[bool] = None) -> None:
        """持续运行，直到调用 stop 或 emergency_stop。"""
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction 必须是 bool 或 None")

        self._start(direction)
        try:
            while not self._should_stop():
                self.pulse_once()
        finally:
            self._finish()

    def stop(self) -> None:
        """请求当前动作停止。"""
        self._stop = True

    def emergency_stop(self) -> None:
        """紧急停止。"""
        self._stop = True
        self._estop = True
        self.disable()

    def cleanup(self) -> None:
        """释放资源。"""
        self.emergency_stop()
        for pin in (self.pul_pin, self.dir_pin, self.ena_pin):
            if pin is None:
                continue
            try:
                pin.close()
            except Exception:
                pass


StepperDriver = Stepper
