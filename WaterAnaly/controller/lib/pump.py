"""Peristaltic pump wrapper built on top of Stepper."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.stepper import Stepper


class Pump(object):
    """Expose pump-oriented actions using a lower-level stepper driver."""

    def __init__(
        self,
        driver: "Stepper",
        dispense_direction: str = "forward",
        aspirate_direction: str = "reverse",
        prime_direction: str | None = None,
        purge_direction: str | None = None,
    ) -> None:
        if driver is None:
            raise ValueError("driver cannot be None")

        self._driver = driver
        # Pump 不自己发脉冲，只负责把“出液/吸液”语义映射成电机方向。
        self._dispense_direction = self._normalize_direction(dispense_direction, "dispense_direction")
        self._aspirate_direction = self._normalize_direction(aspirate_direction, "aspirate_direction")
        if prime_direction is None:
            prime_direction = dispense_direction
        if purge_direction is None:
            purge_direction = dispense_direction
        self._prime_direction = self._normalize_direction(prime_direction, "prime_direction")
        self._purge_direction = self._normalize_direction(purge_direction, "purge_direction")

    def _normalize_direction(self, direction: str, name: str) -> bool:
        if direction == "forward":
            return True
        if direction == "reverse":
            return False
        raise ValueError("%s must be 'forward' or 'reverse'" % name)

    def _normalize_revolutions(self, revolutions: float) -> float:
        if not isinstance(revolutions, (int, float)):
            raise TypeError("revolutions must be a number")
        if revolutions <= 0:
            raise ValueError("revolutions must be > 0")
        return float(revolutions)

    def _normalize_seconds(self, seconds: float) -> float:
        if not isinstance(seconds, (int, float)):
            raise TypeError("seconds must be a number")
        if seconds <= 0:
            raise ValueError("seconds must be > 0")
        return float(seconds)

    def _move_revolutions(self, revolutions: float, direction: bool) -> None:
        # Pump 负责“圈数 -> 步数”换算，再下发给 Stepper 的核心接口 move_steps。
        steps = int(round(self._normalize_revolutions(revolutions) * self._driver.steps_per_rev))
        self._driver.move_steps(steps=steps, direction=direction)

    def _run_for_time(self, seconds: float, direction: bool) -> None:
        # 时间语义仍然复用 Stepper 的底层能力，只是这里补上泵的业务方向。
        self._driver.run_for_time(seconds=self._normalize_seconds(seconds), direction=direction)

    def dispense_revolutions(self, revolutions: float) -> None:
        self._move_revolutions(revolutions, self._dispense_direction)

    def aspirate_revolutions(self, revolutions: float) -> None:
        self._move_revolutions(revolutions, self._aspirate_direction)

    def dispense_for_time(self, seconds: float) -> None:
        self._run_for_time(seconds, self._dispense_direction)

    def aspirate_for_time(self, seconds: float) -> None:
        self._run_for_time(seconds, self._aspirate_direction)

    def prime(self, seconds: float) -> None:
        self._run_for_time(seconds, self._prime_direction)

    def purge(self, seconds: float) -> None:
        self._run_for_time(seconds, self._purge_direction)

    def run_continuous_dispense(self) -> None:
        # 持续运行场景下，由 Stepper 自己处理 stop/emergency_stop。
        self._driver.run_continuous(direction=self._dispense_direction)

    def run_continuous_aspirate(self) -> None:
        self._driver.run_continuous(direction=self._aspirate_direction)

    def stop(self) -> None:
        self._driver.stop()

    def emergency_stop(self) -> None:
        self._driver.emergency_stop()

    def cleanup(self) -> None:
        self._driver.cleanup()
