"""A tiny CPU pairwise ranker. Labels here are declared synthetic utility only."""

from dataclasses import dataclass
import math
import random
import time

from ..contracts import digest, identifier, number
from .model import DOMAIN, FEATURE_NAMES, FEATURE_VERSION


@dataclass(frozen=True)
class ExactEvaluator:
    version: str = "declared-interaction-utility/1"
    domain: str = DOMAIN
    feature_version: str = FEATURE_VERSION
    score_kind: str = "declared_synthetic_utility"

    def contributions(self, value):
        return tuple(zip(FEATURE_NAMES, value.features))

    def score(self, value):
        return value.total


@dataclass(frozen=True)
class AdditiveEvaluator(ExactEvaluator):
    version: str = "independent-card-baseline/1"
    score_kind: str = "isolated_card_points_without_interactions"

    def contributions(self, value):
        return ((FEATURE_NAMES[0], value.isolated_value),)

    def score(self, value):
        return value.isolated_value


@dataclass(frozen=True)
class TrainingGroup:
    family_id: str
    world_digest: str
    features: tuple[tuple[float, ...], ...]
    utilities: tuple[float, ...]
    label_origin: str = "declared_synthetic_utility"

    def __post_init__(self):
        identifier(self.family_id)
        identifier(self.world_digest)
        if self.label_origin != "declared_synthetic_utility":
            raise ValueError("this demonstration does not accept real or inferred expert labels")
        if (not isinstance(self.features, tuple) or not isinstance(self.utilities, tuple)
                or not 2 <= len(self.features) <= 64 or len(self.features) != len(self.utilities)):
            raise ValueError("invalid ranking group")
        for row, utility in zip(self.features, self.utilities):
            if (not isinstance(row, tuple) or len(row) != len(FEATURE_NAMES)
                    or not all(number(x) for x in (*row, utility))):
                raise ValueError("invalid feature or utility")


@dataclass(frozen=True)
class LinearRanker:
    weights: tuple[float, ...]
    scales: tuple[float, ...]
    trained_family_ids: tuple[str, ...]
    training_digest: str
    include_interactions: bool
    seed: int
    epochs: int
    schema_version: str = "synthetic-pairwise-ranker/1"
    version: str = "cpu-pairwise-logistic/1"
    domain: str = DOMAIN
    feature_version: str = FEATURE_VERSION
    score_kind: str = "uncalibrated_learned_rank_score_not_utility_or_probability"
    label_origin: str = "declared_synthetic_utility"

    def __post_init__(self):
        if (self.schema_version != "synthetic-pairwise-ranker/1" or self.domain != DOMAIN
                or self.feature_version != FEATURE_VERSION or self.version != "cpu-pairwise-logistic/1"
                or self.label_origin != "declared_synthetic_utility"
                or self.score_kind != "uncalibrated_learned_rank_score_not_utility_or_probability"):
            raise ValueError("unsupported ranker schema/domain/features")
        if (not isinstance(self.weights, tuple) or not isinstance(self.scales, tuple)
                or len(self.weights) != 3 or len(self.scales) != 3
                or not all(number(x) for x in (*self.weights, *self.scales))
                or any(x <= 0 for x in self.scales)):
            raise ValueError("invalid model coefficients")
        if type(self.include_interactions) is not bool or type(self.seed) is not int:
            raise ValueError("invalid ranker settings")
        if type(self.epochs) is not int or not 1 <= self.epochs <= 2000:
            raise ValueError("invalid training epoch count")
        if (not isinstance(self.trained_family_ids, tuple) or not self.trained_family_ids
                or len(set(self.trained_family_ids)) != len(self.trained_family_ids)):
            raise ValueError("invalid training families")
        identifier(self.training_digest)

    def contributions(self, value):
        return tuple((name, self.weights[i] * x / self.scales[i])
                     for i, (name, x) in enumerate(zip(FEATURE_NAMES, value.features))
                     if i == 0 or self.include_interactions)

    def score(self, value):
        return sum(x for _, x in self.contributions(value))

    @classmethod
    def from_dict(cls, data):
        values = dict(data)
        for key in ("weights", "scales", "trained_family_ids"):
            values[key] = tuple(values[key])
        return cls(**values)


@dataclass(frozen=True)
class FitResult:
    model: LinearRanker
    pairs: int
    initial_loss: float
    final_loss: float
    skipped_ties: int


def fit_ranker(groups, *, include_interactions=True, seed=7, epochs=300,
               learning_rate=0.04, max_seconds=2, cancelled=lambda: False, clock=time.monotonic):
    """Bounded SGD on within-family pair order; normalization uses training only."""
    if (not isinstance(groups, tuple) or not 1 <= len(groups) <= 32
            or len({x.family_id for x in groups}) != len(groups)):
        raise ValueError("provide distinct immutable training families")
    if type(epochs) is not int or not 1 <= epochs <= 2000:
        raise ValueError("epoch budget must be in [1, 2000]")
    if not number(learning_rate) or not 0 < learning_rate <= 1:
        raise ValueError("invalid learning rate")
    if type(include_interactions) is not bool or type(seed) is not int:
        raise ValueError("invalid feature/seed settings")
    if not number(max_seconds) or not 0 < max_seconds <= 30:
        raise ValueError("invalid CPU training time budget")
    deadline = clock() + max_seconds
    scales = tuple(max(1.0, max(abs(row[i]) for group in groups for row in group.features)) for i in range(3))
    pairs, ties = [], 0
    for group in groups:
        for i in range(len(group.features)):
            for j in range(i):
                difference = group.utilities[i] - group.utilities[j]
                if difference == 0:
                    ties += 1
                    continue
                sign = 1 if difference > 0 else -1
                row = tuple(sign * (group.features[i][k] - group.features[j][k]) / scales[k]
                            if k == 0 or include_interactions else 0.0 for k in range(3))
                pairs.append(row)
                if len(pairs) > 4096:
                    raise ValueError("training pair budget exceeded")
    if not pairs:
        raise ValueError("no non-tied training pairs")
    weights = [0.0, 0.0, 0.0]

    def loss():
        result = 0.0
        for row in pairs:
            margin = sum(a * b for a, b in zip(weights, row))
            result += max(0.0, -margin) + math.log1p(math.exp(-abs(margin)))
        return result / len(pairs)

    initial_loss = loss()
    rng = random.Random(seed)
    order = list(range(len(pairs)))
    for _ in range(epochs):
        if cancelled():
            raise ValueError("training_cancelled_no_model_returned")
        rng.shuffle(order)
        if clock() >= deadline:
            raise ValueError("training_budget_exhausted_no_model_returned")
        for offset, index in enumerate(order):
            if offset % 64 == 0 and (cancelled() or clock() >= deadline):
                raise ValueError("training_cancelled_or_budget_exhausted_no_model_returned")
            row = pairs[index]
            margin = sum(a * b for a, b in zip(weights, row))
            gradient = 1.0 / (1.0 + math.exp(max(-60.0, min(60.0, margin))))
            for k in range(3):
                weights[k] += learning_rate * (gradient * row[k] - 0.0001 * weights[k])
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class TrainingData:
        groups: tuple[TrainingGroup, ...]

    model = LinearRanker(tuple(weights), scales, tuple(x.family_id for x in groups),
                         digest(TrainingData(groups)), include_interactions, seed, epochs)
    return FitResult(model, len(pairs), initial_loss, loss(), ties)
