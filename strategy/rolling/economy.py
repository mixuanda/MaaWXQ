"""Explicit strategy assumptions for the option value of unspent resources."""

from dataclasses import dataclass, field

from ..contracts import number


@dataclass(frozen=True)
class EconomyObjective:
    """Value a bounded reserve once at the horizon, never as invented income.

    Defaults preserve the original zero terminal-credit objective. A caller must
    explicitly choose nonzero settings; no WXQ interest or survival rule follows.
    """
    reserve_target: int = 0
    value_per_credit: float = 0
    version: str = field(default="terminal-credit-option/1", init=False)
    origin: str = field(default="declared_strategy_assumption_not_game_rule", init=False)
    units: str = field(default="declared_synthetic_utility_per_reserved_credit", init=False)

    def __post_init__(self):
        if type(self.reserve_target) is not int or not 0 <= self.reserve_target <= 256:
            raise ValueError("reserve target must be an integer in [0, 256]")
        if not number(self.value_per_credit) or self.value_per_credit < 0:
            raise ValueError("reserve valuation must be explicitly finite and nonnegative")
        if not number(self.reserve_target * self.value_per_credit):
            raise ValueError("reserve valuation exceeds finite utility support")

    @property
    def enabled(self):
        return self.reserve_target > 0 and self.value_per_credit > 0

    def terminal_value(self, credits):
        if type(credits) is not int or credits < 0:
            raise ValueError("observed nonnegative credits required")
        value = min(credits, self.reserve_target) * self.value_per_credit
        if not number(value):
            raise ValueError("reserve value overflow")
        return value
