"""Input-free fresh-room checks and cumulative, resumable diagnostic accounting."""
from dataclasses import asdict, dataclass, replace

from runtime.deployment_postcondition import digest
from runtime.lobby import recognize, decide
from strategy.codec import timestamp


def empty_room_pair(before, preaction, *, now):
    """Recompute BOTH snapshots; an old empty room cannot override a new guest.

    The native broker still owns actual dispatch/foreground checks. A later
    empty-only observation never automatically restarts a refused transaction.
    """
    reasons = []; states = []
    for frame in (before, preaction):
        try:
            if (not isinstance(frame.get('sha256'), str) or len(frame['sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in frame['sha256'])):
                raise ValueError('original_room_frame_hash_required')
            state = recognize(frame)
            if (state['scene'] != 'empty_custom_lobby' or state['other_humans_verified_absent'] is not True
                    or state.get('empty_other_slots') != 5):
                reasons.append('current_empty_custom_room_not_proven')
            states.append(state)
        except (KeyError, TypeError, ValueError, AttributeError):
            reasons.append('invalid_room_observation')
    try:
        for key in ('identity_version', 'geometry_version'):
            value = before['identity'][key]
            if not isinstance(value, str) or not value or value != preaction['identity'][key]:
                reasons.append('room_window_changed')
        source = timestamp(before['captured_at']); current = timestamp(preaction['captured_at']); clock = timestamp(now)
        if not source < current <= clock or (clock - current).total_seconds() > 5 or (current - source).total_seconds() > 5:
            reasons.append('room_pair_stale_or_out_of_order')
        if len(states) == 2 and not reasons and decide(states[0]).get('operation') != decide(states[1]).get('operation'):
            reasons.append('room_transition_changed')
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append('room_binding_or_timestamp_invalid')
    return {'status': 'fresh_empty_room_pair' if not reasons else 'room_refused_no_retry',
            'reasons': reasons, 'empty_room_evidence_verified': not reasons,
            'execution_allowed': False, 'automatic_retry_allowed': False}


@dataclass(frozen=True)
class ChainBudget:
    """Cumulative accounting, independent of retained-file count and restarts.

    Charge native attempts BEFORE dispatch, including uncertain/failed attempts.
    Charge actual capture bytes/counts; existing disk reservations remain
    mandatory before input/capture. This helper never captures or deletes files.
    """
    scope_id: str
    started_at: str
    deadline_at: str
    max_captures: int = 50
    max_bytes: int = 64 * 1024 * 1024
    max_native_attempts: int = 28
    captures: int = 0
    capture_bytes: int = 0
    native_attempts: int = 0
    stopped_reason: str = ''

    def __post_init__(self):
        if not isinstance(self.scope_id, str) or not self.scope_id.strip() or len(self.scope_id) > 128:
            raise ValueError('budget_scope_required')
        duration = (timestamp(self.deadline_at) - timestamp(self.started_at)).total_seconds()
        if not 0 < duration <= 600:
            raise ValueError('bounded_original_deadline_required')
        for key, maximum in [('max_captures', 50), ('max_bytes', 64 * 1024 * 1024), ('max_native_attempts', 28)]:
            if type(getattr(self, key)) is not int or not 0 < getattr(self, key) <= maximum:
                raise ValueError('public_budget_limit_exceeded:' + key)
        for key, limit in [('captures', self.max_captures), ('capture_bytes', self.max_bytes), ('native_attempts', self.max_native_attempts)]:
            if type(getattr(self, key)) is not int or not 0 <= getattr(self, key) <= limit:
                raise ValueError('invalid_cumulative_budget_usage:' + key)
        if (self.captures > 0) != (self.capture_bytes > 0):
            raise ValueError('capture_count_and_bytes_must_stay_bound')
        if not isinstance(self.stopped_reason, str) or len(self.stopped_reason) > 256:
            raise ValueError('bounded_stop_reason_required')

    def check_time(self, now):
        if self.stopped_reason:
            raise ValueError('budget_stopped:' + self.stopped_reason)
        if not timestamp(self.started_at) <= timestamp(now) < timestamp(self.deadline_at):
            raise ValueError('original_budget_deadline_reached')

    def charge(self, *, now, captures=0, capture_bytes=0, native_attempts=0):
        self.check_time(now)
        values = (captures, capture_bytes, native_attempts)
        if any(type(v) is not int or v < 0 for v in values) or not any(values):
            raise ValueError('nonempty_nonnegative_budget_charge_required')
        if (captures > 0) != (capture_bytes > 0):
            raise ValueError('capture_count_and_actual_bytes_required_together')
        return replace(self, captures=self.captures + captures, capture_bytes=self.capture_bytes + capture_bytes,
                       native_attempts=self.native_attempts + native_attempts)

    def stop(self, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('stop_reason_required')
        return replace(self, stopped_reason=self.stopped_reason or reason)

    def snapshot(self):
        return asdict(self)

    @classmethod
    def restore(cls, snapshot, *, expected_sha256, now):
        if digest(snapshot) != expected_sha256:
            raise ValueError('budget_checkpoint_changed')
        value = cls(**snapshot)
        value.check_time(now)
        return value
