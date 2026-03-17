"""Stepper motor driver based on PUL / DIR / ENA pins."""

from __future__ import annotations

import time
from typing import Optional, Tuple

from lib.pins import OutputPin


class Stepper(object):
    """Drive a stepper motor with pulse, direction, and optional enable pins."""

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
        if pul_pin is None or dir_pin is None:
            raise ValueError("pul_pin and dir_pin cannot be None")

        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin

        # 这里保存“电机一圈需要多少步”，上层按圈数换算时会用到。
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")
        # 默认按转速自动计算脉冲宽度，也支持后面手动覆盖 pulse_high_s/pulse_low_s。
        self.rpm = 300.0
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
            raise TypeError("%s must be a number" % name)
        if value <= 0:
            raise ValueError("%s must be > 0" % name)
        return float(value)

    def _check_pos_int(self, value, name: str) -> int:
        if not isinstance(value, int):
            raise TypeError("%s must be an int" % name)
        if value <= 0:
            raise ValueError("%s must be > 0" % name)
        return value

    def _check_nonneg_int(self, value, name: str) -> int:
        if not isinstance(value, int):
            raise TypeError("%s must be an int" % name)
        if value < 0:
            raise ValueError("%s must be >= 0" % name)
        return value

    def _pulse_times(self) -> Tuple[float, float]:
        # 如果手动指定了高/低电平持续时间，就优先按手动值输出脉冲。
        if self.pulse_high_s is not None or self.pulse_low_s is not None:
            high_s = self.pulse_high_s
            low_s = self.pulse_low_s

            if high_s is None:
                high_s = self._check_pos_number(low_s, "pulse_low_s")
            if low_s is None:
                low_s = self._check_pos_number(high_s, "pulse_high_s")
            return float(high_s), float(low_s)

        # 否则根据转速和每转步数，自动推导一个 50% 占空比脉冲。
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
            # 没有接 ENA 引脚时，只维护内部状态，不实际写硬件。
            self._enabled = enabled
            return

        if self.ena_low_enable:
            self.ena_pin.write(not enabled)
        else:
            self.ena_pin.write(enabled)
        self._enabled = enabled

    def _start(self, direction: Optional[bool]) -> None:
        # 每次新动作开始时，都清掉上一次的停止标记。
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
        self._set_ena_pin(True)

    def disable(self) -> None:
        self._set_ena_pin(False)

    def set_direction(self, forward: bool) -> None:
        if not isinstance(forward, bool):
            raise TypeError("forward must be bool")
        self._set_dir_pin(forward)

    def set_rpm(self, rpm: float) -> None:
        self.rpm = self._check_pos_number(rpm, "rpm")

    def set_steps_per_rev(self, steps_per_rev: int) -> None:
        self.steps_per_rev = self._check_pos_int(steps_per_rev, "steps_per_rev")

    def pulse_once(self) -> None:
        # 一个完整步进脉冲 = 拉高 + 等待 + 拉低 + 等待。
        high_s, low_s = self._pulse_times()
        self.pul_pin.high()
        time.sleep(high_s)
        self.pul_pin.low()
        time.sleep(low_s)

    def move_steps(self, steps: int, direction: Optional[bool] = None) -> None:
        total_steps = self._check_nonneg_int(steps, "steps")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        self._start(direction)
        try:
            index = 0
            while index < total_steps:
                # stop/emergency_stop 都是在循环检查点生效。
                if self._should_stop():
                    break
                self.pulse_once()
                index += 1
        finally:
            self._finish()

    def run_for_time(self, seconds: float, direction: Optional[bool] = None) -> None:
        duration = self._check_pos_number(seconds, "seconds")
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        self._start(direction)
        deadline = time.time() + duration
        try:
            # 这里不是按步数结束，而是按截止时间结束。
            while time.time() < deadline:
                if self._should_stop():
                    break
                self.pulse_once()
        finally:
            self._finish()

    def run_continuous(self, direction: Optional[bool] = None) -> None:
        if direction is not None and not isinstance(direction, bool):
            raise TypeError("direction must be bool or None")

        self._start(direction)
        try:
            while not self._should_stop():
                self.pulse_once()
        finally:
            self._finish()

    def stop(self) -> None:
        # 正常停止：只设置标记，让当前动作在下一次检查点退出。
        self._stop = True

    def emergency_stop(self) -> None:
        # 急停：除了停止标记，还会立刻失能驱动。
        self._stop = True
        self._estop = True
        self.disable()

    def cleanup(self) -> None:
        # 清理前先急停，避免释放资源时电机还在跑。
        self.emergency_stop()
        for pin in (self.pul_pin, self.dir_pin, self.ena_pin):
            if pin is None:
                continue
            try:
                pin.close()
            except Exception:
                pass
