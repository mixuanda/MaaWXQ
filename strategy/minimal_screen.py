"""Project V5 partial screen state without promoting OCR candidates to facts.

This module has no desktop or input dependency. Replay uses the original capture
time and is deliberately separate from the persistent live Advisor.
"""

from copy import deepcopy
from .codec import timestamp
from .contracts import FieldValue, identifier, number


CORE_FIELDS = ("selected_chess_player_id", "credits", "board_ids", "hand_ids",
               "offer_ids", "capacity", "hand_capacity", "free_board", "free_hand")


def _hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("explicit lowercase frame SHA256 required")
    return value


def _unknown(key):
    return {"key": key, "status": "unknown", "value": None, "confidence": None,
            "confidence_kind": "uncalibrated"}


def _field(key, record):
    """Only an explicitly observed value carries through; candidates remain null."""
    if record.get("status") != "observed":
        return _unknown(key)
    value = {"key": key, **{k: record.get(k) for k in ("status", "value", "confidence")},
             "confidence_kind": record.get("confidence_kind", "uncalibrated")}
    checked = value | {"value": tuple(value["value"]) if isinstance(value["value"], list) else value["value"]}
    FieldValue(**checked)
    return value


def project_minimal(minimal, frame, recognition, *, match_id, now,
                    source_mode="saved_replay", start_match=False):
    """Return a recognition batch plus lossless, non-actionable candidate evidence."""
    identifier(match_id)
    if source_mode not in ("live_capture", "saved_replay") or type(start_match) is not bool:
        raise ValueError("explicit supported source mode and boolean start required")
    if minimal.get("schema") != "maawxq-minimal-state/1":
        raise ValueError("unsupported minimal state schema")
    digest = _hash(frame.get("sha256"))
    source = minimal.get("source", {})
    if (source.get("kind") != "screen_recognition" or source.get("sha256") != digest
            or recognition.get("frame_sha256") != digest):
        raise ValueError("minimal/recognition/source frame mismatch")
    if (minimal.get("captured_at") != frame.get("captured_at")
            or source.get("identity_version") != frame.get("identity", {}).get("identity_version")
            or not source.get("identity_version") or minimal.get("scene") != recognition.get("scene")):
        raise ValueError("minimal capture time, identity or scene mismatch")
    captured, current = timestamp(frame["captured_at"]), timestamp(now)
    processed = timestamp(minimal["processed_at"])
    if not captured <= processed <= current:
        raise ValueError("future or impossible minimal-state timestamp")
    if source_mode == "live_capture" and (minimal.get("source_capture_reused") is not False
                                          or minimal.get("source_mode") != "live_capture"):
        raise ValueError("saved/reused frame cannot enter the live Advisor")
    age = (current-captured).total_seconds()
    active = recognition.get("scene") == "battle_controls" and recognition.get("match_started") is True
    matches = recognition.get("matches", [])
    names = [row.get("name") for row in matches]
    expected = {"battle_settings", "own_portrait", "statistics"}
    positive = (active and len(names) == len(set(names)) and set(names) == expected
                and all(number(row.get("score")) and .95 <= row["score"] <= 1 for row in matches))
    confidence = min(row["score"] for row in matches) if positive else None
    round_field = _field("round", minimal.get("round", {}))
    phase_field = _field("phase", minimal.get("phase", {}))
    round_value, phase_value = round_field["value"], phase_field["value"]
    context_confidence = None
    if round_value is not None and phase_value is not None:
        if type(round_value) is not int or round_value < 0:
            raise ValueError("invalid observed round")
        identifier(phase_value)
        values = [round_field["confidence"], phase_field["confidence"], confidence]
        if all(number(value) for value in values):
            context_confidence = min(values)
    own = {key: _unknown(key) for key in CORE_FIELDS}
    own["selected_chess_player_id"] = _field("selected_chess_player_id", minimal.get("selection", {}).get("confirmed", {}))
    # Energy is not silently equated to the strategy currency. A reviewed semantic
    # mapping may later provide an explicit strategy_fields.credits observation.
    for key, record in minimal.get("strategy_fields", {}).items():
        if key not in own or key == "selected_chess_player_id":
            raise ValueError("unsupported explicit strategy field")
        own[key] = _field(key, record)
    banned = _field("banned_tags", minimal.get("bans", {}))
    batch = {"schema_version": "strategy-recognition-batch/1", "data_kind": "screen_recognition",
             "extractor_version": "minimal-screen-projection/1",
             "frame": {"sha256": digest, "observed_at": frame["captured_at"], "ingested_at": now,
                       "time_basis": ("synchronous_visible_capture" if source_mode == "live_capture"
                                      else "verified_source_frame_timestamp")},
             "scene": {"status": "observed" if positive else "unknown", "value": "battle" if positive else None,
                       "confidence": confidence, "confidence_kind": "uncalibrated"},
             "context": {"match_id": match_id, "round": round_value, "phase": phase_value,
                         "context_confidence": context_confidence,
                         "game_build": _field("game_build", minimal.get("game_build", {}))["value"],
                         "rules_version": _field("rules_version", minimal.get("rules_version", {}))["value"]},
             "start_match": start_match, "own_fields": list(own.values()), "bans": banned, "opponents": []}
    fields = {"round": minimal.get("round", {}), "timer_seconds": minimal.get("timer_seconds", {}),
              "resources.energy": minimal.get("resources", {}).get("energy", {}),
              "selection.confirmed": minimal.get("selection", {}).get("confirmed", {}),
              "phase": minimal.get("phase", {}), "game_build": minimal.get("game_build", {}),
              "rules_version": minimal.get("rules_version", {})}
    for slot in minimal.get("shop", {}).get("slots", []):
        for key in ("name", "entity_id", "cost"):
            fields[f"shop.slots[{slot['slot']}].{key}"] = slot.get(key, {})
    return {"schema_version": "strategy-minimal-projection/1", "recognition_batch": batch,
            "field_evidence": deepcopy(fields), "first_action_requirements": first_purchase_requirements(minimal),
            "provenance": {"source_kind": "screen_recognition", "source_mode": source_mode,
                           "frame_sha256": digest, "captured_at": frame["captured_at"], "processed_at": minimal["processed_at"],
                           "decision_at": now, "age_seconds": age, "replay": source_mode == "saved_replay",
                           "fresh_within_5_seconds": age <= 5},
            "execution_allowed": False}


def first_purchase_requirements(minimal):
    """Concrete smallest gameplay milestone, with each producer's next deliverable."""
    def row(path, present, needed, owner):
        return {"path": path, "current_status": present.get("status", "unknown"),
                "candidate": present.get("candidate"), "confidence": present.get("confidence"),
                "needed": needed, "owner": owner}
    slots = minimal.get("shop", {}).get("slots", [])
    first = next((slot for slot in slots if slot.get("slot") == 1), {})
    return {"milestone": "buy_one_verified_shop_offer_into_a_verified_free_hand_slot",
            "operation": "buy_shop_offer", "implemented_gameplay_handler": True,
            "inputs": [
                row("mode", {}, "positively bound authorized custom match", "scene_recognizer"),
                row("phase", minimal.get("phase", {}), "positive preparation/buy-enabled scene, not a timer inference", "scene_recognizer"),
                row("resources.energy", minimal.get("resources", {}).get("energy", {}), "verified amount plus reviewed mapping to strategy credits", "numeric_recognizer_and_rules"),
                row("shop.slots[1].entity_id", first.get("entity_id", {}), "stable hero ID, current slot, grade and action target bound to this frame", "shop_recognizer"),
                row("shop.slots[1].cost", first.get("cost", {}), "displayed effective cost, discount semantics, and expected resource delta", "shop_recognizer_and_rules"),
                row("hand_slots", {}, "one positively visible legal empty hand slot; do not infer from missing labels", "zone_recognizer")],
            "controller_contract": ["fresh frame, same game identity and exact shop slot hit test",
                                    "one purchase intent with match/frame binding and original five-second expiry",
                                    "independently verify resource delta and destination hero; no blind retry"],
            "later_dynamic_formation_inputs": ["board IDs/positions/grades and capacity", "opponent ID, board coverage and original timestamps", "reviewed unit/synergy/combat utility"],
            "passive_note": "Observed Yi Xing copying is automatic/random at battle start; this is not a manual target action.",
            "scoped_purchase_api": "runtime.purchase.PurchaseHandler",
            "global_combat_model_required_for_this_transaction": False,
            "execution_allowed": False}
