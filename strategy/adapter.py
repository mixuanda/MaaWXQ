"""One-way legacy JSONL bridge. No imports of the shared CLI or UI modules."""

from .codec import timestamp
from .contracts import FieldValue, Observation, Source


def legacy_observation(event, *, event_id, match_id, ingested_at, round=None, phase=None):
    """Caller must add a match_start; legacy source lacks trusted IDs/confidence."""
    kind = event.get("type")
    source = Source("legacy_manual", "legacy-annotation:" + event_id)
    shared = dict(event_id=event_id, match_id=match_id, observed_at=timestamp(event["observed_at"]),
                  ingested_at=ingested_at, source=source, round=round, phase=phase)
    if kind == "opening_bans":
        # Historical lineup labels have no verified semantic ban mapping.
        return Observation(**shared, kind="bans", fields=(FieldValue("banned_tags"),))
    if kind == "opponent_observation":
        opponent_id = event.get("opponent_id")
        if opponent_id == "unknown":
            opponent_id = None
        ids = tuple(x.get("hero_id", "unknown") for x in event["units"])
        known = all(isinstance(x, str) and x and x != "unknown" for x in ids)
        units = FieldValue("unit_ids", "observed", ids) if known else FieldValue("unit_ids")
        return Observation(**shared, kind="opponent", opponent_id=opponent_id, fields=(units,))
    raise ValueError("unsupported legacy event")
