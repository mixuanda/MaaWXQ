"""Version 1 advisory contracts; unknown values are never numeric defaults."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import math

SCHEMA_VERSION = "1.0"
Value = str | int | float | bool | tuple[str, ...] | None


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps require a timezone")
    return value


def identifier(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value == "unknown":
        raise ValueError("a resolved nonempty identifier is required")


def version(value: str) -> None:
    if value != SCHEMA_VERSION:
        raise ValueError("unsupported strategy schema version")


def confidence(value: float | None) -> None:
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                              or not 0 <= value <= 1):
        raise ValueError("confidence must be null or finite in [0, 1]")


def number(value: Value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def to_dict(record) -> dict:
    """JSON-ready output, with stable arrays and ISO timestamps."""
    return json.loads(json.dumps(asdict(record), default=lambda v: aware(v).isoformat(),
                                 allow_nan=False))


def digest(record) -> str:
    encoded = json.dumps(to_dict(record), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Source:
    kind: str
    reference: str

    def __post_init__(self):
        if self.kind not in ("manual_annotation", "legacy_manual", "screen_recognition", "synthetic", "reviewed_rule"):
            raise ValueError("unsupported source kind")
        identifier(self.reference)


@dataclass(frozen=True)
class FieldValue:
    key: str
    status: str = "unknown"
    value: Value = None
    confidence: float | None = None
    confidence_kind: str = "uncalibrated"

    def __post_init__(self):
        identifier(self.key)
        if self.status not in ("observed", "unknown", "ambiguous"):
            raise ValueError("invalid field status")
        if self.status != "observed" and self.value is not None:
            raise ValueError("unknown/ambiguous fields carry null, not a guessed value")
        if self.status == "observed" and self.value is None:
            raise ValueError("observed fields require a value")
        if self.value is not None and type(self.value) not in (str, int, float, bool, tuple):
            raise ValueError("field value must be a scalar or an immutable tuple of IDs")
        if isinstance(self.value, tuple) and any(not isinstance(x, str) or not x for x in self.value):
            raise ValueError("list fields require nonempty strings")
        if type(self.value) is float and not math.isfinite(self.value):
            raise ValueError("nonfinite values are invalid")
        if self.value == "unknown":
            raise ValueError("use status=unknown and value=null")
        confidence(self.confidence)
        if self.confidence_kind != "uncalibrated":
            raise ValueError("this prototype has no calibrated confidence model")


@dataclass(frozen=True)
class Observation:
    event_id: str
    match_id: str
    kind: str
    observed_at: datetime
    ingested_at: datetime
    source: Source
    round: int | None = None
    phase: str | None = None
    fields: tuple[FieldValue, ...] = ()
    opponent_id: str | None = None
    coverage: str = "partial"
    context_confidence: float | None = None
    game_build: str | None = None
    rules_version: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        version(self.schema_version)
        identifier(self.event_id)
        identifier(self.match_id)
        aware(self.observed_at)
        aware(self.ingested_at)
        if self.ingested_at < self.observed_at:
            raise ValueError("ingestion cannot precede observation")
        if self.kind not in ("match_start", "state", "opponent", "bans", "match_end"):
            raise ValueError("unsupported observation kind")
        if self.round is not None and (type(self.round) is not int or self.round < 0):
            raise ValueError("round must be null or a nonnegative integer")
        if self.phase is not None:
            identifier(self.phase)
        if self.opponent_id is not None:
            identifier(self.opponent_id)
        if self.kind != "opponent" and self.opponent_id is not None:
            raise ValueError("opponent identity belongs only to opponent observations")
        if self.coverage not in ("partial", "full"):
            raise ValueError("coverage must be partial or full")
        if not isinstance(self.fields, tuple) or len({x.key for x in self.fields}) != len(self.fields):
            raise ValueError("fields must be an immutable tuple with unique keys")
        confidence(self.context_confidence)
        for item in (self.game_build, self.rules_version):
            if item is not None:
                identifier(item)
        if self.kind == "bans" and (len(self.fields) != 1 or self.fields[0].key != "banned_tags"):
            raise ValueError("ban observations require exactly the banned_tags field")
        if self.kind == "bans" and self.fields[0].status == "observed":
            if not isinstance(self.fields[0].value, tuple):
                raise ValueError("observed bans must be an explicit tuple, including empty")
        if self.kind in ("match_start", "match_end") and self.fields:
            raise ValueError("lifecycle events carry no state fields")


@dataclass(frozen=True)
class EvidenceField:
    field: FieldValue
    event_id: str
    source: Source
    last_seen: datetime
    round: int | None
    phase: str | None


@dataclass(frozen=True)
class OpponentMemory:
    opponent_id: str
    last_seen: datetime
    round: int | None
    coverage: str
    fields: tuple[EvidenceField, ...] = ()


@dataclass(frozen=True)
class MatchState:
    match_id: str | None = None
    state_version: int = 0
    game_build: str | None = None
    rules_version: str | None = None
    lifecycle: str = "unknown"
    round: int | None = None
    phase: str | None = None
    last_seen: datetime | None = None
    context_confidence: float | None = None
    evidence_watermark: datetime | None = None
    fields: tuple[EvidenceField, ...] = ()
    opponents: tuple[OpponentMemory, ...] = ()
    confirmed_bans: tuple[str, ...] = ()
    ban_evidence: EvidenceField | None = None
    ban_version: int = 0
    events: tuple[Observation, ...] = ()
    retired_match_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        version(self.schema_version)


@dataclass(frozen=True)
class BoundPrecondition:
    path: str
    evidence: EvidenceField | None
    operator: str = "known"
    required_value: Value = None


@dataclass(frozen=True)
class ResourceCost:
    path: str
    amount: float

    def __post_init__(self):
        if not self.path.startswith("self.") or self.path.count(".") != 1:
            raise ValueError("cost requires an explicit self resource field")
        if not number(self.amount) or self.amount < 0:
            raise ValueError("cost must be a finite nonnegative number")


@dataclass(frozen=True)
class CandidateAction:
    candidate_id: str
    match_id: str
    state_version: int
    rules_version: str
    rules_digest: str
    rules_domain: str
    ban_version: int
    round: int | None
    phase: str | None
    evidence_watermark: datetime | None
    rule_id: str
    operation: str
    opponent_id: str | None
    ban_tags: tuple[str, ...]
    resource_costs: tuple[ResourceCost, ...]
    preconditions: tuple[BoundPrecondition, ...]
    issued_at: datetime
    expires_at: datetime
    expected_results: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        version(self.schema_version)
        aware(self.issued_at)
        aware(self.expires_at)


@dataclass(frozen=True)
class ScoreComponent:
    path: str
    observed_value: float
    weight: float
    contribution: float
    definition: str
    event_id: str


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: CandidateAction
    accepted: bool
    reasons: tuple[str, ...]
    score: float | None = None
    components: tuple[ScoreComponent, ...] = ()


@dataclass(frozen=True)
class Decision:
    decision_id: str
    match_id: str | None
    state_version: int
    evaluated_at: datetime
    selected: CandidateAction | None
    evaluations: tuple[CandidateEvaluation, ...]
    reasons: tuple[str, ...]
    rules_digest: str
    rules_domain: str
    policy_settings: tuple[tuple[str, Value], ...]
    policy_version: str = "transparent-baseline-1"
    mode: str = field(default="advisory", init=False)
    execution_allowed: bool = field(default=False, init=False)
    score_kind: str = field(default="uncalibrated_heuristic_not_probability", init=False)
    placement_probabilities: None = field(default=None, init=False)
    uncertainty: tuple[str, ...] = field(default=("observation confidence is uncalibrated",
                                                "only the supplied reviewed rule subset is covered",
                                                "heuristic weights and playing strength are unvalidated"), init=False)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        version(self.schema_version)


@dataclass(frozen=True)
class Outcome:
    """Separate outcome channel. This record never updates decision inputs."""

    event_id: str
    match_id: str
    decision_id: str
    candidate_id: str | None
    observed_at: datetime
    source: Source
    actor: str
    execution_status: str
    observed_changes: tuple[FieldValue, ...] = ()
    intervention: bool = False
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        version(self.schema_version)
        for item in (self.event_id, self.match_id, self.decision_id):
            identifier(item)
        if self.candidate_id is not None:
            identifier(self.candidate_id)
        aware(self.observed_at)
        if self.actor not in ("human", "unknown"):
            raise ValueError("this prototype has no execution actor")
        if self.execution_status not in ("not_executed", "observed_change", "uncertain"):
            raise ValueError("unsupported outcome status")
