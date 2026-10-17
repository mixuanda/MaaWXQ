"""Reviewed rule data, never inferred game mechanics."""

from dataclasses import dataclass
import math

from .contracts import SCHEMA_VERSION, ResourceCost, Source, Value, digest, identifier, number, version


@dataclass(frozen=True)
class Requirement:
    path: str
    operator: str = "known"
    value: Value = None

    def __post_init__(self):
        if not self.path.startswith(("self.", "opponent.")) or self.path.count(".") != 1:
            raise ValueError("requirements use self.<field> or opponent.<field>")
        identifier(self.path.split(".")[1])
        if self.operator not in ("known", "eq", "ge"):
            raise ValueError("unsupported precondition operator")
        if self.operator == "ge" and not number(self.value):
            raise ValueError("numeric limits require a finite number")
        if self.operator == "eq" and self.value is None:
            raise ValueError("equality requires an explicit value")


@dataclass(frozen=True)
class ScoreTerm:
    path: str
    weight: float
    definition: str

    def __post_init__(self):
        Requirement(self.path)
        if type(self.weight) not in (int, float) or not math.isfinite(self.weight):
            raise ValueError("score weights must be finite")
        identifier(self.definition)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    operation: str
    verification: str
    source: Source
    phases: tuple[str, ...]
    requirements: tuple[Requirement, ...]
    score_terms: tuple[ScoreTerm, ...]
    expected_results: tuple[str, ...]
    ban_tags: tuple[str, ...] = ()
    targets_opponent: bool = False
    resource_costs: tuple[ResourceCost, ...] = ()

    def __post_init__(self):
        identifier(self.rule_id)
        identifier(self.operation)
        if self.verification not in ("verified", "unverified", "conflicting"):
            raise ValueError("invalid rule verification status")
        if type(self.targets_opponent) is not bool:
            raise ValueError("targets_opponent must be a boolean")
        for values in (self.phases, self.requirements, self.score_terms,
                       self.expected_results, self.ban_tags, self.resource_costs):
            if not isinstance(values, tuple):
                raise ValueError("rule collections must be immutable tuples")
        if not self.phases or not self.requirements or not self.expected_results:
            raise ValueError("rules require phases, prerequisites and expected results")
        for text in (*self.phases, *self.expected_results, *self.ban_tags):
            identifier(text)
        if len({x.path for x in self.score_terms}) != len(self.score_terms):
            raise ValueError("duplicate score fields would double count evidence")
        if len({x.path for x in self.resource_costs}) != len(self.resource_costs):
            raise ValueError("combine costs for the same resource explicitly")
        paths = [x.path for x in self.requirements] + [x.path for x in self.score_terms]
        if any(x.startswith("opponent.") for x in paths) and not self.targets_opponent:
            raise ValueError("opponent evidence requires an explicit opponent target")


@dataclass(frozen=True)
class RuleRegistry:
    game_build: str | None = None
    rules_version: str = "unverified"
    domain: str = "gameplay"
    ban_semantics_verified: bool = False
    rules: tuple[Rule, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        version(self.schema_version)
        identifier(self.rules_version)
        if self.game_build is not None:
            identifier(self.game_build)
        if self.domain not in ("gameplay", "test_rules_not_gameplay"):
            raise ValueError("invalid registry domain")
        if type(self.ban_semantics_verified) is not bool or not isinstance(self.rules, tuple):
            raise ValueError("invalid rule registry")
        if len({x.rule_id for x in self.rules}) != len(self.rules):
            raise ValueError("duplicate rule IDs")
        required_source = "synthetic" if self.domain == "test_rules_not_gameplay" else "reviewed_rule"
        if any(x.source.kind != required_source for x in self.rules):
            raise ValueError("rule provenance does not match registry domain")

    @property
    def fingerprint(self):
        return digest(self)
