"""Current V41 pixels/recognizer results -> existing Advisor recognition contract.

This is a data projection, not a planner. Partial template matches remain partial
zones. It never infers empty slots, bans, levels, stars or odds from missing text.
"""
from copy import deepcopy
from strategy.codec import timestamp
from runtime.surface_gate import _frame, _score
from runtime.name_mask import population_template_gate


def field(key, value=None, confidence=None):
    return dict(key=key, status='unknown' if value is None else 'observed',
                value=value, confidence=None if value is None else confidence)


def bound_record(frame, record):
    if not isinstance(record, dict):
        return None
    if (not frame.get('identity',{}).get('identity_version')
            or record.get('frame_sha256') != frame['sha256']
            or record.get('captured_at',frame['captured_at']) != frame['captured_at']
            or record.get('identity_version') != frame.get('identity', {}).get('identity_version')
            or record.get('geometry_version') != frame.get('identity', {}).get('geometry_version')
            or record.get('status') != 'observed'
            or not _score(record.get('confidence'), .8)):
        return None
    return record


def recognized_zone(frame, name):
    """Only a detector's positively complete zone can supply instance ID tuples.

    Slot kinds: hero / non_hero / empty / unknown. All visible and overflow slots
    must be covered. Free space is supplied by that detector, never counted from
    a small hero-template catalog. Duplicate heroes keep separate instance IDs.
    """
    zone = bound_record(frame, frame.get('recognized_zones', {}).get(name))
    if not zone or zone.get('coverage') != 'full' or zone.get('overflow_checked') is not True:
        return None, {}, {}, 'complete_'+name+'_coverage_unknown'
    slots = zone.get('slots')
    if not isinstance(slots, list) or len(slots) > 32:
        return None, {}, {}, name+'_slots_invalid'
    ids, values, bindings = [], {}, {}
    seen = set()
    for slot in slots:
        if not isinstance(slot, dict): return None, {}, {}, name+'_slot_identity_invalid'
        sid = slot.get('slot_id')
        if not isinstance(sid, str) or not sid or sid in seen:
            return None, {}, {}, name+'_slot_identity_invalid'
        seen.add(sid)
        kind = slot.get('kind')
        if kind in ('empty', 'non_hero'):
            if slot.get('classification_verified') is not True:
                return None, {}, {}, name+'_nonhero_or_empty_unverified'
            continue
        if kind != 'hero' or not isinstance(slot.get('hero_id'), str) or not slot['hero_id']:
            return None, {}, {}, name+'_unresolved_card_or_unit'
        uid = name+':'+sid
        ids.append(uid); values['hero:'+uid] = field('hero:'+uid, slot['hero_id'], zone['confidence'])
        for key in ('star', 'quality_tier', 'unit_level'):
            # Separate named fields; no aliases or numerical substitutions.
            raw = slot.get(key)
            if isinstance(raw, dict) and raw.get('status') == 'observed' and raw.get('semantic_source'):
                value = raw.get('value')
                if type(value) is int and 0 <= value <= 999:
                    values[key+':'+uid] = field(key+':'+uid, value, zone['confidence'])
        if name == 'hand' and slot.get('template_id'):
            bounds=slot.get('bounds')
            if (isinstance(bounds,list)and len(bounds)==4 and all(type(v)is int for v in bounds)
                    and 0<=bounds[0]<bounds[0]+bounds[2]<=1450 and 0<=bounds[1]<bounds[1]+bounds[3]<=869):
                bindings[uid] = dict(status='observed', confidence=zone['confidence'],
                    template_id=slot['template_id'], hero_id=slot['hero_id'],slot_id=sid,
                    bounds=list(bounds),frame_sha256=frame['sha256'],identity_version=frame['identity']['identity_version'],
                    geometry_version=frame['identity']['geometry_version'])
    return ids, values, bindings, None


def project_frame(frame, facts, *, match_id, processed_at, phase,
                  currency_mapping=None, ui=None, source_mode='saved_replay'):
    if source_mode not in ('live_capture', 'offline_replay', 'saved_replay'):
        raise ValueError('explicit_projection_source_mode_required')
    if not _frame(frame) or not timestamp(frame['captured_at']) <= timestamp(processed_at):
        raise ValueError('bound_projection_frame_and_time_required')
    rows = frame.get('matches', [])
    if (not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('name'),str)
            or not _score(row.get('score')) for row in rows) or len({row['name'] for row in rows}) != len(rows)):
        raise ValueError('unique_current_projection_anchors_required')
    scores = {row['name']: row['score'] for row in rows}
    facts_bound = facts.get('frame_sha256') == frame['sha256'] and facts.get('captured_at') == frame['captured_at']
    if not facts_bound:
        facts = dict(energy=None, offers=[], shop_visible=False, round=None, button=None, timer=None)
    # A positive zero-count glyph can prove an empty board. A nonzero count
    # cannot resolve the identities of those units, and never does so here.
    count_rows=frame.get('v14',{}).get('counts',[])
    if (not frame.get('recognized_zones',{}).get('board')
            and population_template_gate(count_rows,expected_count=0,capacity_score=frame.get('v14',{}).get('capacity',0))
            and scores.get('own_portrait',0)>=.985):
        frame=dict(frame,recognized_zones=deepcopy(frame.get('recognized_zones',{})))
        frame['recognized_zones']['board']=dict(status='observed',confidence=max(row['score']for row in count_rows),
            frame_sha256=frame['sha256'],identity_version=frame['identity']['identity_version'],
            geometry_version=frame['identity']['geometry_version'],
            coverage='full',overflow_checked=True,slots=[],source='positive_current_owned_zero_population_glyph')
    ui = ui or {}; own = {}; gaps = []; bindings = {'hand': {}, 'offers': {}, 'actions': {}}
    if not facts_bound: gaps.append('current_facts_frame_binding_unknown')
    def put(key, value=None, confidence=None):
        own[key] = field(key, value, confidence)
    for zone_name in ('board', 'hand'):
        ids, items, targets, gap = recognized_zone(frame, zone_name)
        zone_record=bound_record(frame,frame.get('recognized_zones',{}).get(zone_name))
        put(zone_name+'_ids', ids, zone_record['confidence'] if ids is not None else None)
        own.update(items)
        if zone_name == 'hand': bindings['hand'] = targets
        if gap: gaps.append(gap)
    hand = bound_record(frame, frame.get('recognized_zones', {}).get('hand'))
    free_hand = hand.get('free_slots') if hand and own['hand_ids']['status']=='observed' else None
    put('free_hand', free_hand if type(free_hand) is int and 0 <= free_hand <= 32 else None, .97)
    # Capacity is recognized independently; history of a five-unit board does
    # not turn a missing current glyph into capacity five.
    capacity_score = frame.get('v14', {}).get('capacity', 0)
    capacity_record=bound_record(frame,frame.get('recognized_fields',{}).get('capacity'))
    capacity=capacity_record.get('value') if capacity_record else None
    put('capacity',capacity if type(capacity)is int and 0<=capacity<=32 else None,
        capacity_record['confidence'] if capacity_record else capacity_score)
    currency = None
    if currency_mapping and currency_mapping.get('verified') is True and currency_mapping.get('source'):
        currency = currency_mapping.get('currency_id')
    put('currency_id', currency, .97)
    energy_record=bound_record(frame,frame.get('recognized_fields',{}).get('credits'))
    numeric=frame.get('numbers',{}).get('energy',{})
    energy=(energy_record.get('value') if energy_record else numeric.get('Value')
            if numeric.get('Known')is True and numeric.get('Value')==facts.get('energy') else None)
    put('credits', energy if currency and type(energy) is int and energy >= 0 else None, .97)
    shop = facts.get('shop_visible') is True
    offers = facts.get('offers', []) if shop else []
    complete_slots = len(offers) == 4 and {x.get('slot') for x in offers} == set(range(4))
    hidden = facts.get('shop_hidden_verified') is True and not shop
    put('shop_visible', True if shop else False if hidden else None, .97)
    timer = facts.get('timer')
    put('preparation_seconds', timer if type(timer) is int and 0 <= timer <= 999 else None, .97)
    put('offer_ids', ['shop:'+str(i) for i in range(4)] if shop and complete_slots else [] if hidden else None, .97)
    if shop and complete_slots:
        for offer in offers:
            uid = 'shop:'+str(offer['slot'])
            put('hero:'+uid, offer.get('name'), .97)
            price = offer.get('price')
            put('price:'+uid, price if type(price) is int and price >= 0 else None, .97)
            put('currency:'+uid, currency, .97)
            binding = bound_record(frame, offer.get('ui_binding'))
            if binding and binding.get('hero_id') == offer.get('name'):
                bindings['offers'][uid] = deepcopy(binding)
            for key in ('star', 'quality_tier', 'unit_level'):
                item = offer.get(key)
                if (isinstance(item, dict) and item.get('status')=='observed' and item.get('semantic_source')
                        and type(item.get('value'))is int and 0<=item['value']<=999):
                    put(key+':'+uid, item.get('value'), .97)
    elif not hidden: gaps.append('current_shop_coverage_unknown')
    destination = bound_record(frame, frame.get('recognized_deployment'))
    if destination: bindings['deployment'] = deepcopy(destination)
    for key in ('player_level', 'level_up_cost', 'level_up_target_level', 'refresh_cost'):
        record = bound_record(frame, ui.get(key)) or bound_record(frame,frame.get('recognized_fields',{}).get(key))
        value = record.get('value') if record else None
        put(key, value if type(value) is int and value >= 0 else None, record['confidence'] if record else None)
    for action, key in (('refresh', 'refresh_currency_id'), ('level_up', 'level_up_currency_id')):
        quote_key = 'refresh_cost' if action=='refresh' else 'level_up_cost'
        put(key, currency if own[quote_key]['status']=='observed' else None, .97)
        binding = bound_record(frame, ui.get('actions', {}).get(action))
        if binding: bindings['actions'][action] = deepcopy(binding)
    extra = frame.get('recognized_fields', {})
    for key, raw in extra.items():
        # Current recognizer fields also carry talents/equipment/faction conditions
        # consumed by sourced Affinity rules. They cannot overwrite zone/cost data.
        if key not in own:
            record = bound_record(frame, raw)
            put(key, record.get('value') if record else None, record['confidence'] if record else None)
    bans = bound_record(frame, frame.get('recognized_bans'))
    banned = bans.get('value') if bans and isinstance(bans.get('value'), list) else None
    roundno = facts.get('round')
    current_phase = phase.get('phase') if isinstance(phase, dict) else phase
    selected='phase_start' if facts.get('button')=='开战' else 'phase_ready'
    alternate='phase_ready' if selected=='phase_start' else 'phase_start'
    prep = (current_phase == 'preparation' and type(roundno) is int
            and facts.get('button') in ('准备', '开战')
            and scores.get(selected,0)>=.97 and scores.get(selected,0)-scores.get(alternate,0)>=.02)
    portrait = scores.get('own_portrait',0)
    scene_known = prep and portrait >= .985
    opponents=[]
    for raw in frame.get('recognized_opponents',[]):
        current=bound_record(frame,raw)
        if (not current or current.get('observed_at')!=frame['captured_at']
                or current.get('coverage') not in ('partial','full') or not current.get('opponent_id')):
            continue
        items=[]
        for key,record in current.get('fields',{}).items():
            read=bound_record(frame,record)
            items.append(field(key,read.get('value') if read else None,read['confidence'] if read else None))
        opponents.append(dict(opponent_id=current['opponent_id'],coverage=current['coverage'],fields=items))
    batch = dict(schema_version='strategy-recognition-batch/1', data_kind='screen_recognition',
        extractor_version='v41-current-frame-projection/1',
        frame=dict(sha256=frame['sha256'], observed_at=frame['captured_at'], ingested_at=processed_at,
                   time_basis='synchronous_visible_capture' if source_mode=='live_capture' else 'verified_source_frame_timestamp'),
        scene=dict(status='observed' if scene_known else 'unknown', value='battle' if scene_known else None,
                   confidence=.97 if scene_known else None, confidence_kind='uncalibrated'),
        context=dict(match_id=match_id, round=roundno, phase='preparation' if prep else None,
                     context_confidence=.97 if scene_known else None, game_build=None, rules_version=None),
        start_match=False, own_fields=list(own.values()),
        bans=field('banned_tags', banned, bans['confidence'] if bans else None), opponents=opponents)
    return dict(batch=batch, ui_bindings=bindings, gaps=gaps,
                facts=deepcopy(facts), unknown_fields=[k for k,v in own.items() if v['status']=='unknown'],
                source_mode=source_mode, execution_allowed=False)
