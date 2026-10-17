"""Offline fixture decoder and reproducible multi-round contrast report."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json

from ..contracts import FieldValue, MatchState, Observation, Source, to_dict
from ..policy import Policy
from ..state import reduce_observation
from .model import (DOMAIN, FIELDS, Card, OpponentProfile, PairLink, Position,
                    RoundRule, ThresholdLink, World, validate_position)
from .search import Budget, plan

TEST_POLICY = Policy(allow_test_rules=True)
FIXTURE_TIME = datetime(2030, 1, 1, tzinfo=timezone.utc)


def world_from_dict(record):
    if record.get("domain") != DOMAIN:
        raise ValueError("explicit synthetic world domain required")
    data = dict(record)
    data["cards"] = tuple(Card(**{**x, "roles": tuple(x.get("roles", ())),
                                 "ban_tags": tuple(x.get("ban_tags", ()))}) for x in data["cards"])
    data["pairs"] = tuple(PairLink(**{**x, "units": tuple(x["units"])}) for x in data["pairs"])
    data["thresholds"] = tuple(ThresholdLink(**x) for x in data["thresholds"])
    data["profiles"] = tuple(OpponentProfile(**{**x, "board_ids": tuple(x["board_ids"]),
                                               "disabled_links": tuple(x.get("disabled_links", ())),
                                               "role_adjustments": tuple(tuple(y) for y in x.get("role_adjustments", ()))})
                             for x in data["profiles"])
    data["rounds"] = tuple(RoundRule(**{**x, "offers": None if x["offers"] is None else tuple(x["offers"])})
                           for x in data["rounds"])
    return World(**data)


def make_state(world, *, now=FIXTURE_TIME, board_ids=(), hand_ids=(), offer_ids=(), credits=2,
               capacity=2, hand_capacity=4, discarded_ids=(), round_number=1, bans=(),
               opponent_id="toy-opponent", opponent_board=(), coverage="full", memory_age=0,
               unknown=(), match_id="synthetic-rolling-match"):
    source = Source("synthetic", DOMAIN + ":rolling-fixture")
    start_at = now - timedelta(seconds=max(1, memory_age + 1))
    start = Observation("start", match_id, "match_start", start_at, start_at, source,
                        round=round_number, phase=world.phase, context_confidence=0.95,
                        game_build=world.build, rules_version=world.version)
    state = reduce_observation(MatchState(), start, now=now)
    pos = Position(round_number, credits, tuple(board_ids), tuple(hand_ids), tuple(offer_ids),
                   tuple(discarded_ids), capacity, hand_capacity)
    validate_position(pos, world)
    values = asdict(pos)
    values.update(free_board=pos.free_board, free_hand=pos.free_hand)
    fields = tuple(FieldValue(key) if key in unknown else FieldValue(key, "observed", values[key], 0.95)
                   for key in FIELDS)
    own = Observation("position", match_id, "state", now, now, source, round=round_number,
                      phase=world.phase, context_confidence=0.95, fields=fields)
    state = reduce_observation(state, own, now=now)
    ban_event = Observation("bans", match_id, "bans", now, now, source, round=round_number,
                            phase=world.phase,
                            fields=(FieldValue("banned_tags", "observed", tuple(bans), 0.95),))
    state = reduce_observation(state, ban_event, now=now)
    if opponent_id is not None:
        seen = now - timedelta(seconds=memory_age)
        opponent = Observation("opponent", match_id, "opponent", seen, now, source,
                               round=round_number, phase=world.phase, opponent_id=opponent_id,
                               coverage=coverage,
                               fields=(FieldValue("board_ids", "observed", tuple(opponent_board), 0.95),))
        state = reduce_observation(state, opponent, now=now)
    return state


def load_fixture(path):
    with open(path, encoding="utf-8") as handle:
        fixture = json.load(handle)
    if fixture.get("schema_version") != "toy-rolling-fixture/1" or fixture.get("domain") != DOMAIN:
        raise ValueError("only explicit synthetic fixture schema supported")
    if len(fixture["worlds"]) > 8 or len(fixture["cases"]) > 16:
        raise ValueError("fixture collection exceeds demonstration bound")
    worlds = {name: world_from_dict(value) for name, value in fixture["worlds"].items()}
    return fixture, worlds


def comparison(path, *, allow_test_rules=False):
    fixture, worlds = load_fixture(path)
    if not allow_test_rules:
        return {"schema_version": "rolling-comparison/1", "domain": DOMAIN, "execution_allowed": False,
                "status": "abstain", "reasons": ["test_rules_require_explicit_opt_in"], "cases": []}
    cases = []
    for case in fixture["cases"]:
        world = worlds[case["world"]]
        state = make_state(world, **case["state"])
        result = plan(state, world, "toy-opponent", now=FIXTURE_TIME,
                      budget=Budget(horizon=case["horizon"]), policy=TEST_POLICY)
        data = to_dict(result)
        # Keep the full advice bindings in output, not just a model's label.
        cases.append({"case_id": case["case_id"], "contrast_family": case["contrast_family"],
                      "world_digest": world.fingerprint, "result": data})
    return {"schema_version": "rolling-comparison/1", "domain": DOMAIN, "execution_allowed": False,
            "real_match_results": 0, "real_room_observations": 0, "training_executed": False,
            "related_cases_are_not_independent_matches": True,
            "objective": "sum of declared weighted round utilities minus switching utility costs",
            "future_information": "declared toy offers/income/capacity; all declared opponent profiles",
            "limitations": ["no real rules, combat, chance draws, refunds or survival model",
                            "toy utility is not placement probability or game strength",
                            "future observations require replanning; no continuation is executable"],
            "cases": cases}
