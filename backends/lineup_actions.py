"""Default-off native adapter for one pending Advisor action using existing ports."""
from copy import deepcopy
from datetime import datetime, timezone
import threading

from backends.game_click import Binding, GameClickEvidence, GameClickBroker, NativeUnavailable
from backends.deployment_drag import DeployEvidence, DeploymentDragBroker
from runtime.cleanup import close_verified
from runtime.economy_actions import prepare_action, stamp
from runtime.lineup_transactions import prepare_owned


def _now(): return datetime.now(timezone.utc).isoformat()


class _AdvisedContext:
    def validate_context(self):
        frame, intent, advice = self.lineup_frame, self.lineup_intent, self.lineup_advice
        prepare = prepare_action if intent['action'] in ('refresh', 'level_up') else prepare_owned
        check = prepare(frame, advice, now=intent['prepared_at'])
        expected = {k: v for k, v in intent.items() if k != 'submitted_at'}
        evidence = self.evidence
        start = intent.get('start', intent['target'])
        if (check != expected or not check['ready'] or evidence.frame_sha256 != frame['sha256']
                or (evidence.x, evidence.y) != tuple(start)
                or evidence.context != 'custom_lineup' or evidence.operation != intent['action']
                or evidence.no_other_humans_verified is not True
                or evidence.binding.class_name != 'UnityWndClass'
                or not evidence.executable_path.casefold().endswith('\\wxq.exe')):
            raise NativeUnavailable('pending_Advisor_action_or_target_changed')
        if intent['action'] == 'deploy' and (evidence.end_x, evidence.end_y) != tuple(intent['target']):
            raise NativeUnavailable('advised_deployment_destination_changed')

    def _check(self):
        if self.lineup_cancelled():
            raise NativeUnavailable('manual_pause_or_stop_requested')
        observed = super()._check()
        now = stamp(self.lineup_clock())
        if (not 0 <= (now-stamp(self.lineup_frame['captured_at'])).total_seconds() <= 5
                or now >= stamp(self.lineup_intent['expires_at'])):
            raise NativeUnavailable('advised_action_expired_before_submission')
        return observed


class LineupClickBroker(_AdvisedContext, GameClickBroker):
    pass


class LineupDragBroker(_AdvisedContext, DeploymentDragBroker):
    pass


class GuardedLineupExecutor:
    """Callable dispatch(frame, intent), wired to the real click/drag guards.

    before_input reserves postcondition capture, charges the host's attempt
    budget, checks its pause/stop and current custom-room origin. Its bound
    receipt is checked here. Construction/import performs no Windows calls.
    """
    def __init__(self, bridge, *, observer, before_input, enabled=False, clock=_now, cancelled=lambda: False):
        if type(enabled) is not bool or any(not callable(x) for x in (observer, before_input, cancelled)):
            raise ValueError('explicit_guarded_executor_dependencies_required')
        self.bridge, self.observer, self.before_input = bridge, observer, before_input
        self.enabled, self.clock = enabled, clock
        self.cancelled = cancelled
        self.owner = threading.get_ident()
        self.attempted = set()

    def __call__(self, frame, intent):
        if not self.enabled: raise NativeUnavailable('automatic_input_disabled')
        if threading.get_ident() != self.owner: raise NativeUnavailable('lineup_executor_single_owner_required')
        if self.cancelled(): raise NativeUnavailable('manual_pause_or_stop_requested')
        pending = self.bridge.pending_transaction
        if (not pending or pending.get('intent') != intent or pending['advice'] != self.bridge.last_advice
                or pending['advice']['controller_frame_sha256'] != frame['sha256']):
            raise NativeUnavailable('latched_current_Advisor_transaction_required')
        if pending['id'] in self.attempted: raise NativeUnavailable('native_transaction_already_attempted_no_retry')
        self.attempted.add(pending['id'])  # Consume before any host callback or native arming.
        guard = self.before_input(deepcopy(frame), deepcopy(intent))
        if (not isinstance(guard, dict) or guard.get('custom_room_verified') is not True
                or guard.get('no_other_humans_verified') is not True or guard.get('postcondition_reserved') is not True
                or guard.get('attempt_charged') is not True or guard.get('match_id') != intent['match_id']
                or guard.get('frame_sha256') != frame['sha256']):
            raise NativeUnavailable('host_custom_room_budget_and_postcondition_reservation_required')
        binding = Binding.from_observation(frame['identity'])
        start = intent.get('start', intent['target'])
        shared = dict(context='custom_lineup', operation=intent['action'], no_other_humans_verified=True,
                      scene='current_advised_preparation', recognizer='lineup-current-frame/1',
                      frame_sha256=frame['sha256'], executable_path=frame['identity']['executable_path'])
        if intent['action'] == 'deploy':
            evidence = DeployEvidence(binding, frame['observed_monotonic'], *start, **shared,
                                      end_x=intent['target'][0], end_y=intent['target'][1],
                                      hero_id=intent['hero_id'], match_id=intent['match_id'], capture_utc=frame['captured_at'])
            broker = LineupDragBroker(evidence, observer=self.observer, enabled=True,
                                     utc_clock=lambda: stamp(self.clock()), max_age=5, max_seconds=2)
        else:
            evidence = GameClickEvidence(binding, frame['observed_monotonic'], *start, **shared)
            broker = LineupClickBroker(evidence, observer=self.observer, enabled=True, max_age=5, max_seconds=2)
        broker.lineup_frame, broker.lineup_intent = deepcopy(frame), deepcopy(intent)
        broker.lineup_advice, broker.lineup_clock = deepcopy(pending['advice']), self.clock
        broker.lineup_cancelled = self.cancelled
        finished = False
        try:
            broker.arm()
            started = self.clock()
            submission = broker.drag_once() if intent['action'] == 'deploy' else broker.click_once()
            summary, marker = close_verified(broker)
            finished = True
            # Timestamp is taken after clean release/close and before any capture.
            result = dict(action=intent['action'], before_sha256=frame['sha256'], started_at=started,
                          released_at=self.clock(), submission=deepcopy(submission), native_summary=summary,
                          activity_marker=marker)
            result['submission']['cleanup_errors'] = list(result['submission']['cleanup_errors'])
            if intent['action'] == 'deploy': result['drag_moves'] = deepcopy(broker.port.drag_moves)
            return result
        finally:
            if not finished: broker.close()
