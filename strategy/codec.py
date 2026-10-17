"""Strict JSON boundary for offline annotations and rule registries."""

from datetime import datetime

from .contracts import FieldValue, Observation, ResourceCost, Source, aware
from .rules import Requirement, Rule, RuleRegistry, ScoreTerm


def timestamp(text):
    if not isinstance(text, str):
        raise ValueError("timestamp must be an ISO string")
    return aware(datetime.fromisoformat(text.replace("Z", "+00:00")))


def _value(data):
    return tuple(data) if isinstance(data, list) else data


def observation_from_dict(data):
    if not isinstance(data, dict):
        raise ValueError("observation must be an object")
    if "schema_version" not in data:
        raise ValueError("observation schema_version is required")
    payload = dict(data)
    try:
        payload["observed_at"] = timestamp(payload["observed_at"])
        payload["ingested_at"] = timestamp(payload["ingested_at"])
        payload["source"] = Source(**payload["source"])
        payload["fields"] = tuple(FieldValue(**(dict(x) | {"value": _value(x.get("value"))}))
                                  for x in payload.get("fields", []))
        return Observation(**payload)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid observation fields: " + str(error)) from error


def registry_from_dict(data):
    if not isinstance(data, dict):
        raise ValueError("registry must be an object")
    if "schema_version" not in data:
        raise ValueError("registry schema_version is required")
    payload = dict(data)
    try:
        rules = []
        for raw in payload.get("rules", []):
            item = dict(raw)
            item["source"] = Source(**item["source"])
            item["requirements"] = tuple(Requirement(**(dict(x) | {"value": _value(x.get("value"))}))
                                          for x in item["requirements"])
            item["score_terms"] = tuple(ScoreTerm(**x) for x in item["score_terms"])
            item["resource_costs"] = tuple(ResourceCost(**x) for x in item.get("resource_costs", []))
            for key in ("phases", "expected_results", "ban_tags"):
                item[key] = tuple(item.get(key, []))
            rules.append(Rule(**item))
        payload["rules"] = tuple(rules)
        return RuleRegistry(**payload)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("invalid registry fields: " + str(error)) from error
