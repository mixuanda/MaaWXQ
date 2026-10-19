"""Single-owner lineup feedback loop; construction never captures or sends input."""
from copy import deepcopy
import threading
import uuid

from runtime.economy_actions import prepare_action, values, verify_native_result, stamp
from runtime.lineup_bridge import LineupBridge
from runtime.lineup_transactions import prepare_owned, zone_ids
from strategy.state_projection import project_frame
from runtime.live_perception import state_readiness


def attach_current_state(frame, facts, ocr, *, ui_reader, match_id, processed_at, phase,
                         currency_mapping, source_mode):
    """Join same-frame OCR/measurements; callers must explicitly choose live/replay.

    Recognition providers supply the fact/OCR envelopes themselves. This helper
    never relabels unbound or saved measurements as current screen evidence.
    """
    ui = ui_reader.parse(frame, ocr)
    projection = project_frame(frame, facts, match_id=match_id, processed_at=processed_at,
                               phase=phase, currency_mapping=currency_mapping, ui=ui, source_mode=source_mode)
    result = deepcopy(frame)
    result.update(strategy_batch=projection['batch'], strategy_ui_bindings=projection['ui_bindings'],
                  strategy_projection=projection, source_mode=source_mode)
    result['input_status']=state_readiness(result)
    return result


class LineupRuntime:
    """Buy visible demands, level/search within policy, deploy exact owned units.

    observe supplies a NEW already-projected frame on every call. The default
    dispatcher is GuardedLineupExecutor, retaining existing native guards. A
    private host may supply its existing verified shop-close dispatcher; it must
    return a raw native receipt, not a success boolean. No launch/room creation.
    """
    def __init__(self, policy, *, observe, observer, before_input, clock,
                 enabled=False, close_shop=None):
        from backends.lineup_actions import GuardedLineupExecutor
        self.bridge = LineupBridge(policy)
        self.observe, self.clock, self.close_shop = observe, clock, close_shop
        self.paused = threading.Event(); self.stopped = threading.Event()
        self.enabled = enabled
        self.dispatch = GuardedLineupExecutor(self.bridge, observer=observer, before_input=before_input,
                                             enabled=enabled, clock=clock,
                                             cancelled=lambda: self.paused.is_set() or self.stopped.is_set())
        self.owner = threading.get_ident()
        self.pending_ui = None
        self.last_capture = None

    def pause(self): self.paused.set()
    def resume(self): self.paused.clear()
    def stop(self): self.stopped.set()

    def _read(self):
        if self.paused.is_set() or self.stopped.is_set(): raise ValueError('runtime_paused_or_stopped')
        frame = self.observe()
        captured = stamp(frame['captured_at'])
        if self.last_capture is not None and captured <= self.last_capture:
            raise ValueError('new_capture_required_each_feedback_step')
        self.last_capture = captured
        return frame

    def _close_for_deploy(self, before, advice):
        if self.close_shop is None:
            return dict(status='hold', action='deploy', reason='existing_shop_close_adapter_required')
        own = values(before); context = before['strategy_batch']['context']
        self.pending_ui = dict(action='close_shop', before_frame=before['sha256'], before_time=before['captured_at'],
                               prepared_at=self.clock(), expires_at=advice['expires_at'], before=deepcopy(own),
                               identity_version=before['identity']['identity_version'],
                               geometry_version=before['identity']['geometry_version'],
                               match_id=context['match_id'], round=context['round'])
        # The host closes through its current verified adapter and capture reserve.
        native = self.close_shop(deepcopy(before), deepcopy(advice))
        after = self._read(); intent = self.pending_ui
        reasons = verify_native_result(intent, after, native_result=native, now=self.clock())
        new = values(after)
        if (own.get('shop_visible') is not True or new.get('shop_visible') is not False
                or own.get('credits') != new.get('credits') or own.get('currency_id') != new.get('currency_id')
                or any(zone_ids(own, zone) != zone_ids(new, zone) for zone in ('board', 'hand'))
                or any(new.get('hero:'+uid) != own.get('hero:'+uid)
                       for uid in zone_ids(own, 'board')+zone_ids(own, 'hand'))):
            reasons.append('shop_close_changed_units_or_restored_surface_unknown')
        if reasons:
            return dict(status='submitted_outcome_uncertain_no_retry', reasons=reasons, action='close_shop')
        self.pending_ui = None
        return dict(status='shop_closed_for_advised_deployment', action='close_shop', after_sha256=after['sha256'])

    def step(self):
        if threading.get_ident() != self.owner: raise ValueError('lineup_runtime_single_owner_required')
        if self.stopped.is_set() or self.paused.is_set(): return dict(status='paused_or_stopped')
        if not self.enabled: return dict(status='automatic_input_disabled')
        if self.bridge.pending_transaction is not None or self.pending_ui is not None:
            return dict(status='pending_no_retry')
        try:
            before = self._read(); own = values(before); input_status=state_readiness(before)
            advice = self.bridge.decide(before.get('strategy_batch'), decision_at=self.clock(),
                                        current_frame_sha256=before['sha256'],
                                        source_mode=before.get('source_mode', 'live_capture'))
            action = advice.get('action')
            if action not in ('buy', 'deploy', 'refresh', 'level_up'):
                return dict(status='hold', advice=advice, input_status=input_status)
            seconds = own.get('preparation_seconds')
            if type(seconds) is not int or seconds < 8:
                return dict(status='hold', advice=advice, input_status=input_status,
                            reason='current_preparation_time_insufficient_or_unknown')
            if self.paused.is_set() or self.stopped.is_set(): return dict(status='paused_or_stopped')
            if action == 'deploy' and own.get('shop_visible') is True:
                return self._close_for_deploy(before, advice)
            prepare = prepare_action if action in ('refresh', 'level_up') else prepare_owned
            intent = prepare(before, advice, now=self.clock())
            if not intent['ready']: return dict(intent, status='hold', advice=advice, input_status=input_status)
            transaction_id = uuid.uuid4().hex
            self.bridge.submitted(transaction_id, advice, submitted_at=self.clock(), before_frame=before)
            # Use the exact immutable latch, including preparation/submission time.
            intent = deepcopy(self.bridge.pending_transaction['intent'])
            native = self.dispatch(deepcopy(before), intent)
            after = self._read()
            complete = self.bridge.complete_economy if action in ('refresh', 'level_up') else self.bridge.complete_owned
            result = complete(transaction_id, after, native, now=self.clock())
            return dict(result, action=action, transaction_id=transaction_id, advice=advice,
                        input_status=state_readiness(after))
        except Exception as error:
            pending = self.bridge.pending_transaction is not None or self.pending_ui is not None
            return dict(status='submitted_outcome_uncertain_no_retry' if pending else 'hold',
                        reason=str(error), execution_allowed=False, blind_retry_allowed=False)

    def run(self, *, max_steps):
        """Bounded feedback pass; stop on hold/uncertainty instead of polling UI."""
        if type(max_steps) is not int or not 1 <= max_steps <= 28:
            raise ValueError('bounded_feedback_pass_required')
        results = []
        for _ in range(max_steps):
            result = self.step(); results.append(result)
            if result['status'] not in ('recorded', 'shop_closed_for_advised_deployment'): break
        return results
