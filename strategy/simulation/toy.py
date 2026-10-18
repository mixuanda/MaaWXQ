"""An original bounded fake engine built on the existing pure toy transitions."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import random
import sys
from secrets import token_hex

from ..contracts import FieldValue, Observation, Source, digest
from ..rolling.model import FIELDS, Position, RoundRule, World, move_reasons, moves, transition
from ..rolling.search import StepTrace
from .contracts import (AuditEvent, EpisodeMetadata, IllegalAction, PlayerView, SimAction,
                        SimulatorError, StepReceipt, TerminalResult)
from .fixtures import CARDS, PAIRS, PROFILES, SUPPORTED, THRESHOLDS, UNKNOWN, scenario_by_id

PLAYER = "player-0"
OPPONENT = "opponent-0"
RULES_VERSION = "synthetic-simulator-rules/1"
BASELINE_COMMIT = "eff3dcd367aed9a53e90325f7810d13ded62b8a2"
EPOCH = datetime(2030, 1, 1, tzinfo=timezone.utc)


def source_digest():
    """Bind uncommitted engine source and reused transition code, without paths."""
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "simulation").glob("*.py"))
    files += [root / "rolling/model.py", root / "contracts.py", root / "state.py"]
    value = hashlib.sha256()
    for path in files:
        value.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        value.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return value.hexdigest()


@dataclass(frozen=True)
class AuditState:
    metadata: EpisodeMetadata
    position: Position
    revision: int
    hidden_offers: tuple[tuple[str, ...], ...]
    opponent_hand: tuple[str, ...]
    rng_state: tuple
    terminal: TerminalResult | None


class ToySimulator:
    """One controlled seat; a passive opponent exposes only a fixed public board.

    Finite, pre-generated hidden offers are fixture randomness, not a model of
    the real shop. No combat or placement is implemented. Reset cannot reuse an
    instance; instantiate a new adapter for the next episode.
    """

    def __init__(self):
        self._metadata = None

    def reset(self, seed, scenario):
        if self._metadata is not None:
            raise SimulatorError("one_episode_per_instance")
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("seed must be an unsigned 64-bit integer")
        spec = scenario_by_id(scenario)
        rng = random.Random(seed)
        sequences = []
        for _ in range(spec.rounds):
            sequence = [x.unit_id for x in CARDS]
            rng.shuffle(sequence)
            sequences.append(tuple(sequence))
        opponent_hand = ("private-reserve-" + str(rng.randrange(1000000)),)
        metadata = EpisodeMetadata(
            "original-toy-simulator", "original-synthetic-adapter/2", None,
            source_digest(), ".".join(map(str, sys.version_info[:3])), BASELINE_COMMIT,
            RULES_VERSION, spec.scenario_id,
            digest(spec), seed, SUPPORTED, UNKNOWN, "episode-" + token_hex(16))
        self._spec, self._rng, self._hidden = spec, rng, tuple(sequences)
        self._opponent_hand = opponent_hand
        self._revision = 0
        self._terminal = None
        self._events = (AuditEvent(0, "reset"),)
        self._position = Position(1, spec.credits, ("unit-a",), (), (), (),
                                  spec.capacity, spec.hand_capacity)
        self._position = replace(self._position, offer_ids=self._offers(1, self._position))
        self._world = self._make_world(self._position)
        self._metadata = metadata
        self._observations = self._snapshot(start=True)
        return metadata

    def _ready(self, player=None):
        if self._metadata is None:
            raise SimulatorError("reset_required")
        if player is not None and player != PLAYER:
            raise SimulatorError("unsupported_player")

    def _offers(self, round_number, position):
        unavailable = set(position.board_ids + position.hand_ids + position.discarded_ids)
        available = tuple(x for x in self._hidden[round_number - 1] if x not in unavailable)
        return tuple(sorted(available[:self._spec.offers_per_round]))

    def _make_world(self, position):
        # Future frames exist only inside the engine. The policy sees one frame.
        frames = tuple(RoundRule(r, self._spec.income,
                                 position.offer_ids if r == position.round else (),
                                 self._spec.capacity, 1)
                       for r in range(1, self._spec.rounds + 1))
        return World(RULES_VERSION, CARDS, PAIRS, THRESHOLDS, PROFILES, frames,
                     1, 1, 0, verification="declared_synthetic",
                     build="synthetic-adapter-build-1")

    def _snapshot(self, *, start=False):
        pos = self._position
        now = EPOCH + timedelta(seconds=self._revision + 1)
        shared = dict(match_id=self._metadata.episode_id, observed_at=now, ingested_at=now,
                      source=Source("synthetic", "synthetic-fixture:adapter/1"),
                      round=pos.round, phase=self._world.phase, context_confidence=1,
                      game_build=self._world.build, rules_version=self._world.version)

        def event(suffix, kind, **extra):
            return Observation(event_id=str(self._revision) + ":" + suffix,
                               kind=kind, **shared, **extra)

        values = {**asdict(pos), "free_board": pos.free_board, "free_hand": pos.free_hand}
        records = (event("start", "match_start"),) if start else ()
        records += (
            event("state", "state", coverage="full", fields=tuple(
                FieldValue(name, "observed", values[name], 1) for name in FIELDS)),
            event("bans", "bans", fields=(FieldValue("banned_tags", "observed", self._spec.bans, 1),)),
            event("opponent", "opponent", opponent_id=OPPONENT, coverage="full",
                  fields=(FieldValue("board_ids", "observed", PROFILES[0].board_ids, 1),)),
        )
        if self._terminal is not None:
            records += (event("end", "match_end"),)
        return records

    def observe(self, player):
        self._ready(player)
        frame = RoundRule(self._position.round, self._spec.income,
                          self._position.offer_ids, self._position.capacity, 1)
        public_world = replace(self._world, rounds=(frame,))
        return PlayerView(player, self._revision, self._observations, public_world, self._metadata.episode_id)

    def legal_actions(self, player):
        self._ready(player)
        if self._terminal is not None:
            return ()
        return tuple(SimAction(player, self._revision, move, self._metadata.episode_id) for move in moves(self._position)
                     if not move_reasons(self._position, self._world, move, self._spec.bans))

    def step(self, action):
        self._ready()
        if (not isinstance(action, SimAction) or action.episode_id != self._metadata.episode_id
                or action not in self.legal_actions(PLAYER)):
            raise IllegalAction("illegal_stale_or_terminal_action")
        before = self._position
        world = self._world
        if action.move.kind == "end_round" and before.round < self._spec.rounds:
            offers = self._offers(before.round + 1, before)
            world = replace(world, rounds=tuple(
                replace(frame, offers=offers) if frame.round == before.round + 1 else frame
                for frame in world.rounds))
        outcome = transition(before, world, action.move, bans=self._spec.bans,
                             final_round=self._spec.rounds)
        after = outcome.position
        if after.credits != before.credits - outcome.credits_spent + outcome.income_received:
            raise SimulatorError("resource_conservation_failed")
        ledger = StepTrace(before.round, action.move.label, before.credits, after.credits,
                           after.round, before.board_ids, after.board_ids, after.discarded_ids,
                           outcome.switching_cost, outcome.credits_spent, outcome.income_received,
                           after.hand_ids, after.offer_ids, after.capacity)
        terminal = (TerminalResult(before.round, after.credits, after.board_ids)
                    if outcome.terminal else None)
        # All legality/transition checks above are pure; commit only a valid result.
        self._position, self._world, self._terminal = after, world, terminal
        self._revision += 1
        self._events += (AuditEvent(self._revision, "step", action, ledger),)
        self._observations += self._snapshot()
        return StepReceipt(self._revision, terminal is not None)

    def export_events(self):
        self._ready()
        return self._events

    def terminal_result(self):
        self._ready()
        return self._terminal

    def audit_snapshot(self):
        """TEST AUDIT ONLY. Deliberately excluded from SimulatorAdapter/PlayerView."""
        self._ready()
        return AuditState(self._metadata, self._position, self._revision, self._hidden,
                          self._opponent_hand, self._rng.getstate(), self._terminal)
