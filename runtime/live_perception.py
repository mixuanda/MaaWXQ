"""Normalize one supplied capture/measurement bundle for the V42 host contract.

No capture backend, OCR, Windows import or fallback is selected here. The sole
host owns acquisition; a common transport envelope never proves slot coverage.
"""
from copy import deepcopy

from runtime.economy_actions import stamp
from runtime.surface_gate import _frame
from runtime.surface_gate import _score
from strategy.state_projection import bound_record


def _tokens(frame):
    return dict(frame_sha256=frame['sha256'], captured_at=frame['captured_at'],
                identity_version=frame['identity']['identity_version'],
                geometry_version=frame['identity']['geometry_version'])


def _bind(record, tokens):
    if not isinstance(record, dict): raise ValueError('recognition_record_object_required')
    result = deepcopy(record)
    for key, value in tokens.items():
        if key in result and result[key] != value:
            raise ValueError('mixed_capture_recognition:'+key)
        result[key] = value
    return result


def normalize_bundle(bundle, *, now, previous_capture=None):
    """Return frame/facts/ocr/phase for LiveProviders.capture, without IO.

    Optional recognition is a perception-frame/1 envelope with zones, fields,
    bans, opponents, deployment, close_shop, match_origin, facts and phase.
    Supplied status/confidence/coverage/empty/semantic proofs are kept verbatim.
    Missing recognition stays missing; no hero catalog or successful-action
    history is used to fill it.
    """
    if not isinstance(bundle, dict): raise ValueError('capture_bundle_required')
    result = deepcopy(bundle); frame = result.get('frame')
    if (not isinstance(frame,dict) or not _frame(frame) or frame.get('source_mode') != 'live_capture'
            or frame.get('source_capture_reused') is True):
        raise ValueError('new_original_live_capture_required')
    captured = stamp(frame['captured_at'])
    if not 0 <= (stamp(now)-captured).total_seconds() <= 5:
        raise ValueError('live_capture_stale_or_future')
    if previous_capture is not None and captured <= stamp(previous_capture):
        raise ValueError('live_capture_time_must_advance')
    tokens = _tokens(frame); envelope = result.get('recognition')
    if envelope is not None:
        if not isinstance(envelope, dict) or envelope.get('schema_version') != 'perception-frame/1':
            raise ValueError('perception_frame_schema_required')
        if any(envelope.get(key) != value for key,value in tokens.items()):
            raise ValueError('recognition_envelope_must_match_capture')
        def assign(key, value):
            if key in frame and frame[key] != value:
                raise ValueError('conflicting_current_recognition:'+key)
            frame[key] = value
        for source, destination in (('zones','recognized_zones'), ('fields','recognized_fields')):
            rows = envelope.get(source)
            if rows is not None:
                if not isinstance(rows, dict) or len(rows) > 512:
                    raise ValueError('bounded_recognition_dictionary_required:'+source)
                if source == 'zones' and set(rows)-{'board','hand'}:
                    raise ValueError('unknown_owned_zone')
                assign(destination, {key:_bind(record,tokens) for key,record in rows.items()})
        for source, destination in (('bans','recognized_bans'), ('deployment','recognized_deployment'),
                                    ('close_shop','recognized_shop_close'), ('match_origin','recognized_match_origin')):
            if source in envelope: assign(destination, _bind(envelope[source],tokens))
        if 'opponents' in envelope:
            rows = envelope['opponents']
            if not isinstance(rows,list) or len(rows)>16: raise ValueError('bounded_opponents_required')
            opponents=[]
            for row in rows:
                item=_bind(row,tokens)
                # A current message carrying an older opponent view cannot
                # renew it. The actual observation time remains mandatory.
                if item.get('observed_at') != frame['captured_at']:
                    raise ValueError('opponent_original_observation_time_required')
                item['fields']={key:_bind(value,tokens) for key,value in item.get('fields',{}).items()}
                opponents.append(item)
            assign('recognized_opponents',opponents)
        if 'facts' in envelope:
            facts=_bind(envelope['facts'],tokens)
            offers=facts.get('offers',[])
            if not isinstance(offers,list) or len(offers)>4: raise ValueError('bounded_shop_facts_required')
            for offer in offers:
                if not isinstance(offer,dict): raise ValueError('offer_object_required')
                if 'ui_binding' in offer: offer['ui_binding']=_bind(offer['ui_binding'],tokens)
            if 'facts' in result and result['facts']!=facts:
                raise ValueError('conflicting_current_facts')
            result['facts']=facts
        if 'phase' in envelope:
            if 'phase' in result and result['phase']!=envelope['phase']:
                raise ValueError('conflicting_current_phase')
            result['phase']=deepcopy(envelope['phase'])
    # Deliberately do not add frame/time to missing facts or OCR. Projection
    # reports unknown for unbound data instead of promoting a default value.
    result.setdefault('facts',{}); result.setdefault('ocr',{}); result.setdefault('phase',None)
    for name in ('facts','ocr'):
        value=result[name]
        if not isinstance(value,dict): raise ValueError('current_'+name+'_object_required')
        if value and (value.get('frame_sha256')!=frame['sha256'] or value.get('captured_at')!=frame['captured_at']):
            raise ValueError('mixed_capture_'+name)
    return result


class LivePerceptionAdapter:
    """Wrap the host's existing authorized provider; no worker is started here."""
    def __init__(self, capture_and_measure, *, clock):
        if not callable(capture_and_measure) or not callable(clock):
            raise ValueError('existing_capture_provider_and_clock_required')
        self.capture_and_measure, self.clock = capture_and_measure, clock
        self.last_capture = None

    def __call__(self, path, regions, anchors):
        raw=self.capture_and_measure(path, regions, anchors)
        result=normalize_bundle(raw,now=self.clock(),previous_capture=self.last_capture)
        self.last_capture=result['frame']['captured_at']
        return result


def state_readiness(frame):
    """Specific missing inputs for operator/host diagnostics, never a permit."""
    batch=frame.get('strategy_batch',{}); known={}
    for row in batch.get('own_fields',[]):
        if (row.get('status')=='observed' and row.get('value') is not None
                and _score(row.get('confidence'),.8)):
            known[row['key']]=row['value']
    missing=lambda keys:[key for key in keys if key not in known]
    decision=missing(('board_ids','hand_ids','offer_ids','capacity'))
    bans=batch.get('bans',{})
    if bans.get('status')!='observed' or bans.get('value') is None or not _score(bans.get('confidence'),.8):
        decision.append('current_match_bans')
    scene=batch.get('scene',{}); context=batch.get('context',{})
    if scene.get('value')!='battle' or scene.get('status')!='observed' or context.get('phase')!='preparation':
        decision.append('current_preparation_context')
    bindings=frame.get('strategy_ui_bindings',{})
    resources=missing(('credits','currency_id','preparation_seconds'))
    actions={
        'buy':missing(('free_hand',)),
        'deploy':[],
        'refresh':missing(('player_level','refresh_cost','refresh_currency_id','free_hand')),
        'level_up':missing(('player_level','level_up_target_level','level_up_cost','level_up_currency_id')),
    }
    if not bindings.get('offers'):actions['buy'].append('current_purchasable_offer_binding')
    if not bindings.get('hand'):actions['deploy'].append('physical_owned_hand_binding')
    if not bindings.get('deployment'):actions['deploy'].append('legal_empty_own_board_destination')
    for action in ('refresh','level_up'):
        if not bindings.get('actions',{}).get(action):actions[action].append('current_enabled_'+action+'_binding')
    for action in actions:actions[action]=sorted(set(decision+resources+actions[action]))
    host_missing=[]
    origin=bound_record(frame,frame.get('recognized_match_origin'))
    if not origin or origin.get('continuity_verified') is not True:host_missing.append('current_match_origin_continuity')
    if known.get('shop_visible') is True and not bound_record(frame,frame.get('recognized_shop_close')):
        host_missing.append('current_reviewed_shop_close_binding')
    return dict(schema_version='lineup-input-status/1',decision_missing=sorted(set(decision)),
                action_missing=actions, host_missing=host_missing,observed_fields=sorted(known),
                unknown_fields=sorted(row['key'] for row in batch.get('own_fields',[]) if row['key'] not in known),
                perception_gaps=list(frame.get('strategy_projection',{}).get('gaps',[])),
                diagnostic_only=True,execution_allowed=False)
