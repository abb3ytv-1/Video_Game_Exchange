from enum import Enum


class GameCreateCondition(str, Enum):
    FAIR = "fair"
    GOOD = "good"
    MINT = "mint"
    POOR = "poor"

    def __str__(self) -> str:
        return str(self.value)
