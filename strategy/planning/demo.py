"""Reproducible CPU demonstration with explicit synthetic label provenance."""

from itertools import combinations
import math
import statistics
import time

from ..codec import timestamp
from ..contracts import to_dict
from .candidates import TEST_POLICY
from .model import (Card, DOMAIN, FEATURE_NAMES, Interaction, Scenario, ToyWorld,
                    formation_value, make_state)
from .ranker import AdditiveEvaluator, ExactEvaluator, TrainingGroup, fit_ranker
from .search import Budget, plan


def world_from_dict(data):
    values = dict(data)
    if values.get("domain") != DOMAIN or values.get("schema_version") != "toy-planning-world/1":
        raise ValueError("an explicit synthetic world schema/domain is required")
    values["cards"] = tuple(Card(**(dict(x) | {"roles": tuple(x.get("roles", [])),
                                              "ban_tags": tuple(x.get("ban_tags", []))}))
                            for x in values["cards"])
    values["interactions"] = tuple(Interaction(**(dict(x) | {"requires": tuple(x["requires"])}))
                                   for x in values.get("interactions", []))
    return ToyWorld(**values)


def case_state(world, case, now):
    permitted = {"board_ids", "hand_ids", "offer_ids", "credits", "capacity", "hand_capacity", "bans", "unknown"}
    if set(case["position"]) - permitted:
        raise ValueError("unsupported position field")
    state = make_state(world, now=now, **case["position"])
    scenarios = tuple(Scenario(**(dict(x) | {"disabled_interactions": tuple(x.get("disabled_interactions", []))}))
                      for x in case.get("scenarios", [{"scenario_id": "declared_toy_opponent"}]))
    return state, scenarios


def training_groups(data):
    groups = []
    for family in data["training_families"]:
        world = world_from_dict(family["world"])
        if world.verification != "declared_synthetic":
            raise ValueError("unverified training world")
        capacity = family["capacity"]
        if type(capacity) is not int or not 1 <= capacity <= 3:
            raise ValueError("training formation capacity must be in [1, 3]")
        rows, utilities = [], []
        ids = tuple(x.card_id for x in world.cards)
        for count in range(capacity + 1):
            for board in combinations(ids, count):
                value = formation_value(world, board)
                rows.append(value.features)
                utilities.append(value.total)
        groups.append(TrainingGroup(family["family_id"], world.fingerprint, tuple(rows), tuple(utilities)))
    return tuple(groups)


def comparison(data, *, allow_test_rules=False, timing_repeats=3):
    if data.get("schema_version") != "synthetic-planning-benchmark/1" or data.get("domain") != DOMAIN:
        raise ValueError("unsupported benchmark schema/domain")
    if not allow_test_rules:
        return {"domain": DOMAIN, "execution_allowed": False, "training_executed": False,
                "selected": None, "reasons": ["test_rules_require_explicit_opt_in"]}
    if type(timing_repeats) is not int or not 1 <= timing_repeats <= 10:
        raise ValueError("timing repetitions must be in [1, 10]")
    world = world_from_dict(data["heldout_world"])
    groups = training_groups(data)
    heldout_family = data["split_manifest"]["heldout_family"]
    if (heldout_family in {x.family_id for x in groups}
            or set(data["split_manifest"]["training_families"]) != {x.family_id for x in groups}
            or world.fingerprint in {x.world_digest for x in groups}):
        raise ValueError("training/heldout family overlap or manifest mismatch")
    settings = data["training_settings"]
    started = time.perf_counter()
    cpu_started = time.process_time()
    trained = fit_ranker(groups, **settings)
    ablated = fit_ranker(groups, include_interactions=False, **settings)
    training_seconds = time.perf_counter() - started
    training_cpu_seconds = time.process_time() - cpu_started
    evaluators = {"independent_card_baseline": AdditiveEvaluator(),
                  "interaction_depth_one": ExactEvaluator(), "interaction_depth_two": ExactEvaluator(),
                  "cpu_ranker_depth_two": trained.model, "ranker_without_interactions": ablated.model}
    now = timestamp(data["decision_at"])
    timings = {key: [] for key in evaluators}
    cases = []
    regrets = {key: [] for key in evaluators}
    for case in data["cases"]:
        state, scenarios = case_state(world, case, now)
        outputs = {}
        for name, evaluator in evaluators.items():
            depth = 1 if name == "interaction_depth_one" else 2
            for index in range(timing_repeats):
                start = time.perf_counter()
                result = plan(state, world, now=now, policy=TEST_POLICY, scenarios=scenarios,
                              budget=Budget(max_depth=depth, max_seconds=1), evaluator=evaluator)
                timings[name].append((time.perf_counter() - start) * 1000)
                if index == 0:
                    selected = next((x for x in result.alternatives
                                     if result.selected and x.first_action == result.selected), None)
                    outputs[name] = {"selected": result.selected.label if result.selected else None,
                                     "status": result.status, "path": result.contingent_path,
                                     "termination": result.termination, "nodes": result.nodes,
                                     "declared_toy_utility": min(x.declared_toy_utility for x in selected.leaves)
                                     if selected else None,
                                     "formation": selected.predicted_board if selected else None,
                                     "composition_breakdown": {
                                         "leaves": [to_dict(x) for x in selected.leaves],
                                         "interactions_gained": selected.interactions_gained,
                                         "interactions_lost": selected.interactions_lost,
                                         "remaining_credits": selected.predicted_credits
                                     } if selected else None,
                                     "hard_rejections": result.root_rejections,
                                     "root_supported_actions": result.root_actions,
                                     "reasons": result.reasons, "final_gate": result.final_gate}
        reference = outputs["interaction_depth_two"]
        for name, output in outputs.items():
            if (reference["termination"] == "complete" and output["termination"] == "complete"
                    and reference["declared_toy_utility"] is not None and output["declared_toy_utility"] is not None):
                regret = reference["declared_toy_utility"] - output["declared_toy_utility"]
                output["synthetic_oracle_regret"] = regret
                regrets[name].append(regret)
        cases.append({"case_id": case["case_id"], "family_id": heldout_family, "results": outputs})

    def latency(values):
        ordered = sorted(values)
        return {"samples": len(values), "p50_ms": statistics.median(values),
                "p95_ms": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]}

    return {"schema_version": "synthetic-planning-report/1", "domain": DOMAIN,
            "execution_allowed": False, "training_executed": True,
            "label_origin": "declared_synthetic_formation_utility_not_expert_or_game_results",
            "real_labeled_decisions": 0, "real_match_results": 0,
            "split_manifest": data["split_manifest"],
            "related_contrast_cases_are_not_independent_matches": True,
            "feature_semantics": "Declared pair/higher-order interactions are supplied to the model; it does not discover game rules.",
            "training": {"settings": settings, "feature_version": trained.model.feature_version,
                         "feature_order": FEATURE_NAMES,
                         "cpu_seconds_for_both_fits": training_cpu_seconds,
                         "wall_seconds_for_both_fits": training_seconds,
                         "interaction_fit": to_dict(trained), "ablation_fit": to_dict(ablated)},
            "latency": {name: latency(values) for name, values in timings.items()},
            "quality": {name: {"supported_contrasts": len(values),
                                "abstentions": sum(x["results"][name]["selected"] is None for x in cases),
                                "fallbacks": sum(x["results"][name]["status"] == "fallback" for x in cases),
                                "mean_synthetic_utility_regret": statistics.mean(values) if values else None}
                        for name, values in regrets.items()},
            "cases": cases,
            "limitations": ["Toy utility agreement and CPU latency are engineering results, not Yixing playing strength.",
                            "All related contrasts share one heldout synthetic family; no statistical match-performance inference is valid.",
                            "Real rules, opponent transitions, expert labels and independent matches remain missing."]}
