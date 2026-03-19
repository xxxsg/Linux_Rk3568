"""基于 PUL / DIR / ENA 引脚的步进电机驱动。"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from lib.pins import Pin


class Stepper:
    """通过脉冲、方向和使能引脚控制步进电机。

    该类关注底层电机驱动逻辑，支持按步数、按时间和连续运行三种控制方式。
    """

    def __init__(
        self,
        pul_pin: Pin,
        dir_pin: Pin,
        ena_pin: Optional[Pin] = None,
        steps_per_rev: int = 800,
    ) -> None:
        """初始化步进驱动对象并设置默认运行参数。

        参数:
            pul_pin: 脉冲输出引脚
            dir_pin: 方向控制引脚
            ena_pin: 使能引脚，可选
            steps_per_rev: 电机每圈对应的步数
        """
        if pul_pin is None or dir_pin is None:
            raise ValueError("pul_pin and dir_pin cannot be None")

        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")

        self.rpm = 300.0
        self.pulse_high_s: Optional[float] = None
        self.pulse_low_s: Optional[float] = None

        self.dir_high_forward = True
        self.ena_low_enable = True
        self.auto_enable = True
        self.forward = True

        self._stop = False
        self._estop = False
        self._enabled = False

        self.disable()

    def _check_pos_number(self, value, name: str) -> float:
        """校验正数参数。"""
        if not isinstance(value, (int, float)):
            raise TypeError("%s must be a number" % name)
        if value <= 0:
            raise ValueError("%s must be > 0" % name)
        return float(value)

    def _check_pos_int(self, value, name: str) -> int:
        """校验正整数参数。"""
        if not isinstance(value, int):
            raise TypeError("%s must be an int" % name)
        if value <= 0:
            raise ValueError("%s must be > 0" % name)
        return value

    def _check_nonneg_int(self, value, name: str) -> int:
        """校验非负整数参数。"""
        if not isinstance(value, int):
            raise TypeError("%s must be an int" % name)
        if value < 0:
            raise ValueError("%s must be >= 0" % name)
        return value

    def _pulse_times(self) -> Tuple[float, float]:
        """计算单步脉冲高低电平持续时间。"""
        if self.pulse_high_s is not None or self.pulse_low_s is not None:
            high_s = self.pulse_high_s if self.pulse_high_s is not None else self._check_pos_number(self.pulse_low_s, "pulse_low_s")
            low_s = self.pulse_low_s if self.pulse_low_s is not None else self._check_pos_number(self.pulse_high_s, "pulse_high_s")
            return float(high_s), float(low_s)

        period = 60.0 / (self._check_pos_number(self.rpm, "rpm") * self._check_pos_int(self.steps_per_rev, "steps_per_rev"))
        return period / 2.0, period / 2.0

    def _apply_direction(self, forward: bool) -> None:
        """根据方向极性配置输出 DIR 电平。"""
        self.dir_pin.write(forward if self.dir_high_forward else not forward)
        self.forward = bool(forward)

    def _apply_enable(self, enabled: bool) -> None:
        """根据使能极性配置输出 ENA 电平。"""
        if self.ena_pin is None:
            self._enabled = enabled
            return
        self.ena_pin.write(not enabled if self.ena_low_enable else enabled)
        self._enabled = enabled

    def _begin_motion(self, direction: Optional[bool]) -> None:
        """开始运动前复位停止标志，并按需设置方向/使能。"""
        self._stop = False
        self._estop = False
        if direction is not None:
            self.set_direction(direction)
        if self.auto_enable:
            self.enable()

    def _end_motion(self) -> None:
        """结束运动后按配置自动关闭使能。"""
        if self.auto_enable:
            self.disable()

    def _should_stop(self) -> bool:
        """判断当前是否收到停止请求。"""
        return self._stop or self._estop

    def enable(self) -> None:
        """使能电机驱动。"""
        self._apply_enable(True)

    def disable(self) -> None:
        """关闭电机驱动使能。"""
        self._apply_enable(False)

    def set_dir_active_level(self, high_is_forward: bool) -> None:
        """设置 DIR 高电平是否表示正转。"""
        if not isinstance(high_is_forward, bool):
            raise TypeError("high_is_forward must be bool")
        self.dir_high_forward = high_is_forward
        self._apply_direction(self.forward)

    def set_enable_active_level(self, low_is_enable: bool) -> None:
        """设置 ENA 低电平是否表示使能。"""
        if not isinstance(low_is_enable, bool):
            raise TypeError("low_is_enable must be bool")
        was_enabled = self._enabled
        self.ena_low_enable = low_is_enable
        self._apply_enable(was_enabled)

    def set_auto_enable(self, enabled: bool) -> None:
        """设置运动开始/结束时是否自动控制使能。"""
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")
        self.auto_enable = enabled

    def configure_driver(
        self,
        *,
        dir_high_forward: Optional[bool] = None,
        ena_low_enable: Optional[bool] = None,
        auto_enable: Optional[bool] = None,
    ) -> None:
        """集中配置驱动极性与自动使能策略。

        参数均可传 `None`，表示保持当前配置不变。
        """
        if dir_high_forward is not None:
            self.set_dir_active_level(dir_high_forward)
        if ena_low_enable is not None:
            self.set_enable_active_level(ena_low_enable)
        if auto_enable is not None:
            self.set_auto_enable(auto_enable)

    def set_direction(self, forward: bool) -> None:
        """设置运动方向。"""
        if not isinstance(forward, bool):
            raise TypeError("forward must be bool")
        self._apply_direction(forward)

    def set_rpm(self, rpm: float) -> None:
        """设置电机转速，单位 RPM。"""
        self.rpm = self._check_pos_number(rpm, "rpm")

    def set_steps_per_rev(self, steps_per_rev: int) -> None:
        """设置电机每圈步数。"""
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")

    def pulse_once(self) -> None:
        """输出一个完整步进脉冲。"""
        high_s, low_s = self._pulse_times()
        self.pul_pin.high()
        time.sleep(high_s)
        self.pul_pin.low()
        time.sleep(low_s)

    def move_steps(self, steps: int, direction: Optional[bool] = None) -> None:
        """按指定步数运行。

        参数:
            steps: 需要执行的步数，必须大于等于 0
            direction: 传入时先切换方向，再开始运行
        """
        total_steps = self._check_nonneg_int(steps, "steps")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        self._begin_motion(direction)
        try:
            for _ in range(total_steps):
                if self._should_stop():
                    break
                self.pulse_once()
        finally:
            self._end_motion()

    def run_for_time(self, seconds: float, direction: Optional[bool] = None) -> None:
        """按指定时长运行。

        参数:
            seconds: 运行时长，单位秒
            direction: 传入时先切换方向，再开始运行
        """
        duration = self._check_pos_number(seconds, "seconds")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        self._begin_motion(direction)
        deadline = time.time() + duration
        try:
            while time.time() < deadline:
                if self._should_stop():
                    break
                self.pulse_once()
        finally:
            self._end_motion()

    def run_continuous(self, direction: Optional[bool] = None) -> None:
        """持续运行，直到收到停止请求。

        参数:
            direction: 传入时先切换方向，再开始运行
        """
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        self._begin_motion(direction)
        try:
            while not self._should_stop():
                self.pulse_once()
        finally:
            self._end_motion()

    def stop(self) -> None:
        """请求当前运动在下一个步进周期停止。"""
        self._stop = True

    def emergency_stop(self) -> None:
        """立即停止并关闭使能。"""
        self._stop = True
        self._estop = True
        self.disable()

    def cleanup(self) -> None:
        """执行急停并释放相关引脚资源。"""
        self.emergency_stop()
        for pin in (self.pul_pin, self.dir_pin, self.ena_pin):
            if pin is None:
                continue
            try:
                pin.close()
            except Exception:
                pass
