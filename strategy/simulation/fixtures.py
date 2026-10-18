"""Anonymous, original, fixed synthetic fixtures; no WXQ rule claims."""

from dataclasses import dataclass

from ..rolling.model import Card, OpponentProfile, PairLink, ThresholdLink


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    credits: int
    bans: tuple[str, ...] = ()
    rounds: int = 3
    income: int = 1
    capacity: int = 2
    hand_capacity: int = 2
    offers_per_round: int = 2


SCENARIOS = (
    Scenario("synthetic-economy-v1", 3),
    Scenario("synthetic-zero-budget-v1", 0),
    Scenario("synthetic-banned-v1", 3, ("unit-c",)),
)
CARDS = (
    Card("unit-a", 1, 1, ("group-x",)),
    Card("unit-b", 5, 2, ("group-y",)),
    Card("unit-c", 2, 1, ("group-x",)),
    Card("unit-d", 3, 2, ("group-x",)),
    Card("unit-e", 4, 3, ("group-y",)),
)
PAIRS = (PairLink("pair-ac", ("unit-a", "unit-c"), 5),)
THRESHOLDS = (ThresholdLink("two-x", "group-x", 2, 2),)
PROFILES = (OpponentProfile("passive", ("public-marker",)),)
SUPPORTED = (
    "single controlled seat and passive opponent",
    "synthetic buy/deploy/replace/hold/end_round",
    "integer credits, capacity, discard without refund and entry income",
    "fixed synthetic bans, pair and threshold utilities",
    "seeded hidden round offers, public opponent board and private reserve",
    "revision-bound actions and atomic illegal-action rejection",
)
UNKNOWN = (
    "real shop tiers, odds, shared pool, refresh, lock, sale and upgrade experience",
    "real combat, damage scaling, fight duration and tie resolution",
    "Yixing copy triggers, limits, persistence and version applicability",
    "real synergy thresholds, skills, equipment, targeting and event order",
    "real income, interest, health, elimination, placement and opponent scheduling",
)


def scenario_by_id(scenario_id):
    for scenario in SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise ValueError("unsupported synthetic scenario")
