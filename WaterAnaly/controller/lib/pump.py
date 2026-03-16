"""蠕动泵业务层。"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from lib.stepper import Stepper


class Pump(object):
    """蠕动泵业务封装。"""

    def __init__(
        self,
        driver: "Stepper",
        dispense_direction: str = "forward",
        aspirate_direction: str = "reverse",
        prime_direction: Optional[str] = None,
        purge_direction: Optional[str] = None,
    ) -> None:
        if driver is None:
            raise ValueError("driver 不能为空")

        self._driver = driver
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
        raise ValueError("%s 只能是 'forward' 或 'reverse'" % name)

    def dispense_revolutions(self, revolutions: Optional[float] = None) -> None:
        """按圈数执行排液。"""
        self._driver.move_revolutions(revolutions=revolutions, direction=self._dispense_direction)

    def aspirate_revolutions(self, revolutions: Optional[float] = None) -> None:
        """按圈数执行吸液。"""
        self._driver.move_revolutions(revolutions=revolutions, direction=self._aspirate_direction)

    def dispense_for_time(self, seconds: Optional[float] = None) -> None:
        """按时间执行排液。"""
        self._driver.run_for_time(seconds=seconds, direction=self._dispense_direction)

    def aspirate_for_time(self, seconds: Optional[float] = None) -> None:
        """按时间执行吸液。"""
        self._driver.run_for_time(seconds=seconds, direction=self._aspirate_direction)

    def prime(self, seconds: Optional[float] = None) -> None:
        """预充液路。"""
        self._driver.run_for_time(seconds=seconds, direction=self._prime_direction)

    def purge(self, seconds: Optional[float] = None) -> None:
        """清洗或排空液路。"""
        self._driver.run_for_time(seconds=seconds, direction=self._purge_direction)

    def run_continuous_dispense(self) -> None:
        """连续排液，直到外部调用 stop。"""
        self._driver.run_continuous(direction=self._dispense_direction)

    def run_continuous_aspirate(self) -> None:
        """连续吸液，直到外部调用 stop。"""
        self._driver.run_continuous(direction=self._aspirate_direction)

    def stop(self) -> None:
        """请求当前动作停止。"""
        self._driver.stop()

    def emergency_stop(self) -> None:
        """紧急停止。"""
        self._driver.emergency_stop()

    def cleanup(self) -> None:
        """释放底层资源。"""
        self._driver.cleanup()


PeristalticPump = Pump
