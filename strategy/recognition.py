"""Convert an explicit recognizer batch into match evidence, without inventing rules."""

from dataclasses import asdict
import hashlib
import json

from .codec import observation_from_dict, registry_from_dict
from .contracts import FieldValue, identifier, number
from .session import _object


def input_requirements(registry_record, *, controller_operations=None):
    """Give the real extractor exact field dependencies from the supplied registry."""
    registry = registry_from_dict(registry_record)
    if controller_operations is not None:
        if not isinstance(controller_operations, (tuple, list)):
            raise ValueError("controller operation inventory must be a sequence")
        for operation in controller_operations:
            identifier(operation)
    rules = []
    for rule in registry.rules:
        paths = sorted({item.path for item in (*rule.requirements, *rule.score_terms, *rule.resource_costs)})
        rules.append({"rule_id": rule.rule_id, "operation": rule.operation,
                      "rule_source": asdict(rule.source), "targets_opponent": rule.targets_opponent,
                      "ban_tags": list(rule.ban_tags),
                      "verification": rule.verification, "phases": list(rule.phases),
                      "field_paths": paths, "requirements": [asdict(item) for item in rule.requirements],
                      "resource_costs": [asdict(item) for item in rule.resource_costs],
                      "score_terms": [asdict(item) for item in rule.score_terms],
                      "controller_operation_supported": (rule.operation in controller_operations
                                                         if controller_operations is not None else None)})
    gaps = []
    if registry.domain != "gameplay":
        gaps.append("synthetic_registry_not_real_gameplay")
    if not registry.rules:
        gaps.append("reviewed_gameplay_rules_missing")
    if registry.game_build is None or registry.rules_version == "unverified":
        gaps.append("client_build_or_rules_version_unverified")
    if not registry.ban_semantics_verified:
        gaps.append("ban_scope_and_effect_unverified")
    return {"schema_version": "strategy-recognition-requirements/1", "rules_digest": registry.fingerprint,
            "domain": registry.domain, "game_build": registry.game_build, "rules_version": registry.rules_version,
            "core_inputs": ["positive_active_battle_scene", "semantic_observation_time_and_basis",
                            "frame_sha256_and_extractor_version", "match_local_identity",
                            "round_phase_context_confidence", "client_build_and_rules_version",
                            "explicit_ban_evidence_with_reviewed_semantics"],
            "rules": rules, "gaps": gaps,
            "model_limits": {"dynamic_cost_expressions": False, "combat_outcome_model": False,
                             "game_ui_postcondition_contract": False}, "execution_allowed": False}


def frame_records(batch, *, min_scene_confidence=0.8):
    """A menu/unknown frame or host-only acquisition never creates battle events."""
    _object(batch, ("schema_version", "data_kind", "extractor_version", "frame", "scene",
                    "context", "start_match", "own_fields", "bans", "opponents"), "recognition batch")
    if batch.get("schema_version") != "strategy-recognition-batch/1":
        raise ValueError("unsupported recognition batch schema")
    kind = batch.get("data_kind")
    if kind not in ("screen_recognition", "synthetic"):
        raise ValueError("explicit screen_recognition or synthetic data kind required")
    identifier(batch.get("extractor_version"))
    frame = _object(batch.get("frame"), ("sha256", "observed_at", "ingested_at", "time_basis"), "frame")
    frame_hash = frame.get("sha256")
    if not isinstance(frame_hash, str) or len(frame_hash) != 64 or any(ch not in "0123456789abcdef" for ch in frame_hash):
        raise ValueError("an explicit lowercase frame SHA256 is required")
    if not number(min_scene_confidence) or not 0 <= min_scene_confidence <= 1:
        raise ValueError("scene confidence threshold must be finite in [0, 1]")
    scene_data = _object(batch.get("scene"), ("status", "value", "confidence", "confidence_kind"), "scene")
    scene = FieldValue(key="scene", **scene_data)
    gaps = []
    if (scene.status != "observed" or scene.value != "battle" or scene.confidence is None
            or scene.confidence < min_scene_confidence):
        gaps.append("active_battle_not_observed")
    if frame.get("observed_at") is None:
        gaps.append("semantic_observation_time_unknown")
    if frame.get("time_basis") not in ("synchronous_visible_capture", "verified_source_frame_timestamp"):
        gaps.append("source_frame_freshness_unverified")
    if gaps:
        return {"status": "pending_recognition", "records": [], "blocking_gaps": gaps,
                "frame_sha256": frame_hash, "execution_allowed": False}
    context = _object(batch.get("context"), ("match_id", "round", "phase", "game_build", "rules_version",
                                            "context_confidence"), "battle context")
    identifier(context.get("match_id"))
    start = batch.get("start_match", False)
    if type(start) is not bool:
        raise ValueError("start_match must be an explicit boolean")
    fields = batch.get("own_fields", [])
    opponents = batch.get("opponents", [])
    if not isinstance(fields, list) or not isinstance(opponents, list) or len(opponents) > 16:
        raise ValueError("explicit field and bounded opponent arrays required")
    prefix = "frame-" + hashlib.sha256(json.dumps(batch, sort_keys=True, allow_nan=False).encode()).hexdigest()
    source = {"kind": kind, "reference": "frame:" + frame_hash + ":extractor:" + batch["extractor_version"]
              + ":time_basis:" + frame["time_basis"]}
    base = {"schema_version": "1.0", **context, "observed_at": frame["observed_at"],
            "ingested_at": frame["ingested_at"], "source": source}
    records = []
    if start:
        records.append({**base, "event_id": prefix + ":start", "kind": "match_start"})
    records.append({**base, "event_id": prefix + ":self", "kind": "state", "fields": fields})
    if "bans" in batch:
        records.append({**base, "event_id": prefix + ":bans", "kind": "bans", "fields": [batch["bans"]]})
    identities = set()
    for index, opponent in enumerate(opponents):
        _object(opponent, ("opponent_id", "coverage", "fields"), "opponent")
        identity = opponent.get("opponent_id")
        identifier(identity)
        if identity in identities:
            raise ValueError("duplicate opponent identity in one frame")
        identities.add(identity)
        records.append({**base, **opponent, "event_id": prefix + ":opponent:" + str(index), "kind": "opponent"})
    for record in records:
        observation_from_dict(record)
    return {"status": "observed", "records": records, "blocking_gaps": [],
            "frame_sha256": frame_hash, "execution_allowed": False}


def ingest_frame(advisor, batch, *, now, min_scene_confidence=0.8):
    """Apply one complete frame atomically, or revoke an old intent on uncertainty."""
    try:
        result = frame_records(batch, min_scene_confidence=min_scene_confidence)
        if result["blocking_gaps"]:
            advisor.invalidate(";".join(result["blocking_gaps"]), now=now)
            return result | {"event_receipts": []}
        receipt = advisor.observe_batch(result["records"], now=now)
        return result | {"event_receipts": receipt["receipts"]}
    except (ValueError, KeyError, TypeError):
        advisor.invalidate("recognition_batch_invalid", now=now)
        raise
