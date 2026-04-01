"""基于 Stepper 的蠕动泵封装。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.stepper import Stepper


class Pump:
    """基于底层步进电机驱动，提供更贴近泵语义的操作接口。

    Stepper 负责硬件层方向极性定义；
    Pump 只关心业务语义里的“吸液方向”。
    排液方向始终由吸液方向自动取反，避免出现互相矛盾的配置。
    """

    def __init__(
        self,
        driver: "Stepper",
        aspirate_direction: str = "reverse",
    ) -> None:
        """初始化泵对象。

        `aspirate_direction` 表示“吸液”时电机应使用的方向：
        - `"forward"`: direction=True 时表示吸液
        - `"reverse"`: direction=False 时表示吸液

        “排液/出液”方向会自动使用相反方向，不需要单独配置。
        """
        if driver is None:
            raise ValueError("driver cannot be None")

        self._driver = driver
        self._aspirate_direction = self._parse_direction(aspirate_direction, "aspirate_direction")
        # 排液方向固定与吸液方向相反，避免配置出互相冲突的两个方向。
        self._dispense_direction = not self._aspirate_direction

    def _parse_direction(self, direction: str, name: str) -> bool:
        """将字符串方向转换为步进驱动使用的布尔方向值。"""
        if direction == "forward":
            return True
        if direction == "reverse":
            return False
        raise ValueError("%s must be 'forward' or 'reverse'" % name)

    def _normalize_revolutions(self, revolutions: float) -> float:
        """校验并规范化圈数参数。"""
        if not isinstance(revolutions, (int, float)):
            raise TypeError("revolutions must be a number")
        if revolutions <= 0:
            raise ValueError("revolutions must be > 0")
        return float(revolutions)

    def _normalize_seconds(self, seconds: float) -> float:
        """校验并规范化运行时长参数。"""
        if not isinstance(seconds, (int, float)):
            raise TypeError("seconds must be a number")
        if seconds <= 0:
            raise ValueError("seconds must be > 0")
        return float(seconds)

    def dispense_steps(self, steps: int) -> None:
        """按步数执行排液。

        参数:
            steps: 排液对应的步数，必须大于等于 0
        """
        if not isinstance(steps, int):
            raise TypeError("steps must be an int")
        if steps < 0:
            raise ValueError("steps must be >= 0")
        self._driver.move_steps(steps=steps, direction=self._dispense_direction)

    def aspirate_steps(self, steps: int) -> None:
        """按步数执行吸液。

        参数:
            steps: 吸液对应的步数，必须大于等于 0
        """
        if not isinstance(steps, int):
            raise TypeError("steps must be an int")
        if steps < 0:
            raise ValueError("steps must be >= 0")
        self._driver.move_steps(steps=steps, direction=self._aspirate_direction)

    def dispense_revolutions(self, revolutions: float) -> None:
        """按圈数执行排液。

        参数:
            revolutions: 排液圈数，必须大于 0
        """
        steps = int(round(self._normalize_revolutions(revolutions) * self._driver.steps_per_rev))
        self._driver.move_steps(steps=steps, direction=self._dispense_direction)

    def aspirate_revolutions(self, revolutions: float) -> None:
        """按圈数执行吸液。

        参数:
            revolutions: 吸液圈数，必须大于 0
        """
        steps = int(round(self._normalize_revolutions(revolutions) * self._driver.steps_per_rev))
        self._driver.move_steps(steps=steps, direction=self._aspirate_direction)

    def dispense_time(self, seconds: float) -> None:
        """按时长执行排液。

        参数:
            seconds: 排液时长，单位秒，必须大于 0
        """
        self._driver.run_for_time(seconds=self._normalize_seconds(seconds), direction=self._dispense_direction)

    def aspirate_time(self, seconds: float) -> None:
        """按时长执行吸液。

        参数:
            seconds: 吸液时长，单位秒，必须大于 0
        """
        self._driver.run_for_time(seconds=self._normalize_seconds(seconds), direction=self._aspirate_direction)

    def dispense_continuous(self) -> None:
        """持续排液，直到外部调用停止。"""
        self._driver.run_continuous(direction=self._dispense_direction)

    def aspirate_continuous(self) -> None:
        """持续吸液，直到外部调用停止。"""
        self._driver.run_continuous(direction=self._aspirate_direction)

    def stop(self) -> None:
        """停止运动。"""
        self._driver.stop()

    def cleanup(self) -> None:
        """清理底层驱动及相关引脚资源。"""
        self._driver.cleanup()
