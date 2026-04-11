"""基于 PUL / DIR 引脚的步进电机驱动。"""

from __future__ import annotations

import time
from typing import Optional, Tuple

from .pins import Pin


class Stepper:
    """通过脉冲和方向引脚控制步进电机。

    该类关注底层电机驱动逻辑，支持按步数、按时间和连续运行三种控制方式。
    通过控制脉冲发送实现启停，ENA引脚悬空。
    """

    def __init__(
        self,
        pul_pin: Pin,
        dir_pin: Pin,
        steps_per_rev: int = 800,
    ) -> None:
        """初始化步进驱动对象并设置默认运行参数。

        参数:
            pul_pin: 脉冲输出引脚
            dir_pin: 方向控制引脚
            steps_per_rev: 电机每圈对应的步数
        """
        if pul_pin is None or dir_pin is None:
            raise ValueError("pul_pin and dir_pin cannot be None")

        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")

        self.rpm = 300.0
        self.pulse_high_s: Optional[float] = None
        self.pulse_low_s: Optional[float] = None

        self.dir_high_forward = True
        self.forward = True

        self._stop = False

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
        """根据方向极性配置输出 DIR 电平（共阳极时取反）。"""
        self.dir_pin.write(not (forward if self.dir_high_forward else not forward))
        self.forward = bool(forward)

    def _should_stop(self) -> bool:
        """判断当前是否收到停止请求。"""
        return self._stop

    def set_dir_active_level(self, high_is_forward: bool) -> None:
        """设置 DIR 高电平是否表示正转。"""
        if not isinstance(high_is_forward, bool):
            raise TypeError("high_is_forward must be bool")
        self.dir_high_forward = high_is_forward
        self._apply_direction(self.forward)

    def configure_driver(
        self,
        *,
        dir_high_forward: Optional[bool] = None,
    ) -> None:
        """集中配置驱动极性。

        参数均可传 `None`，表示保持当前配置不变。
        """
        if dir_high_forward is not None:
            self.set_dir_active_level(dir_high_forward)

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
        """输出一个完整步进脉冲（共阳极，低电平触发）。"""
        high_s, low_s = self._pulse_times()
        self.pul_pin.low()
        time.sleep(low_s)
        self.pul_pin.high()
        time.sleep(high_s)

    def move_steps(self, steps: int, direction: Optional[bool] = None) -> None:
        """按指定步数运行。

        参数:
            steps: 需要执行的步数，必须大于等于 0
            direction: 传入时先切换方向，再开始运行
        """
        total_steps = self._check_nonneg_int(steps, "steps")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        # 开始运动前复位停止标志，并按需设置方向
        self._stop = False
        if direction is not None:
            self.set_direction(direction)

        try:
            for _ in range(total_steps):
                if self._should_stop():
                    break
                self.pulse_once()
        finally:
            # 结束运动后的处理
            pass

    def run_for_time(self, seconds: float, direction: Optional[bool] = None) -> None:
        """按指定时长运行。

        参数:
            seconds: 运行时长，单位秒
            direction: 传入时先切换方向，再开始运行
        """
        duration = self._check_pos_number(seconds, "seconds")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        # 开始运动前复位停止标志，并按需设置方向
        self._stop = False
        if direction is not None:
            self.set_direction(direction)

        deadline = time.time() + duration
        try:
            while time.time() < deadline:
                if self._should_stop():
                    break
                self.pulse_once()
        finally:
            # 结束运动后的处理
            pass

    def run_continuous(self, direction: Optional[bool] = None) -> None:
        """持续运行，直到收到停止请求。

        参数:
            direction: 传入时先切换方向，再开始运行
        """
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        # 开始运动前复位停止标志，并按需设置方向
        self._stop = False
        if direction is not None:
            self.set_direction(direction)

        try:
            while not self._should_stop():
                self.pulse_once()
        finally:
            # 结束运动后的处理
            pass

    def stop(self) -> None:
        """停止运动。"""
        self._stop = True

    def cleanup(self) -> None:
        """执行停止并释放相关引脚资源。"""
        self.stop()
        for pin in (self.pul_pin, self.dir_pin):
            if pin is None:
                continue
            try:
                pin.close()
            except Exception:
                pass
