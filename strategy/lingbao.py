"""Observed Lingbao catalog + explicit selection/budgets -> existing lineup API.

No lineup names, heroes, spending defaults, odds or merge recipes are built in.
Incomplete input returns named gaps and no runnable policy.
"""
from copy import deepcopy

from strategy.codec import timestamp
from strategy.contracts import Source
from strategy.lineup import Lineup, Target, Spending
from runtime.surface_gate import _score


BUDGETS=('reserve','upgrade_reserve','level_reserve','refresh_spend_cap','refresh_count_cap')


def compile_lingbao_selection(catalog, selection, spending, *, now):
    gaps=[]; plans=[]; names={}
    def gap(path):
        if path not in gaps:gaps.append(path)
    def pending():return dict(status='pending',policy=None,gaps=gaps,display_names=names,execution_allowed=False)
    if not isinstance(catalog,dict) or catalog.get('schema_version')!='lingbao-catalog/1':
        gap('observed_lingbao_catalog');return pending()
    frame=catalog.get('frame',{})
    if not isinstance(frame,dict):frame={}
    digest=frame.get('sha256')
    try:
        if (not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)
                or not isinstance(frame.get('identity_version'),str) or not frame['identity_version']
                or not isinstance(frame.get('geometry_version'),str) or not frame['geometry_version']
                or timestamp(frame['captured_at'])>timestamp(now)
                or catalog.get('recommendation_provider')!='in_game_lingbao'):
            gap('catalog_original_frame_and_provider')
    except (KeyError,ValueError,TypeError,AttributeError):gap('catalog_original_capture_time')
    if not isinstance(selection,dict):selection={}
    selected=selection.get('plan_ids')
    if (not isinstance(selected,list) or not 1<=len(selected)<=16 or any(not isinstance(x,str)or not x for x in selected)
            or len(set(selected))!=len(selected)):
        gap('explicit_selected_plan_ids');selected=[]
    if not isinstance(selection.get('reference'),str) or not selection['reference'].strip():gap('selection_reference')
    levels=selection.get('search_min_levels',{})
    if not isinstance(levels,dict) or any(key not in selected for key in levels):
        gap('search_level_policy_for_selected_plans');levels={}
    if not isinstance(spending,dict):spending={}
    if spending.get('budget_scope')!='match':gap('spending.budget_scope')
    if not isinstance(spending.get('reference'),str) or not spending['reference'].strip():gap('spending.reference')
    for key in BUDGETS:
        if type(spending.get(key))is not int or spending[key]<0:gap('spending.'+key)
    rows=catalog.get('plans')
    if not isinstance(rows,list) or len(rows)>16:
        gap('bounded_observed_catalog_plans');return pending()
    ids=[row.get('lineup_id') if isinstance(row,dict) else None for row in rows]
    if any(not isinstance(x,str)or not x for x in ids) or len(set(ids))!=len(ids):
        gap('unique_catalog_plan_ids');return pending()
    tokens=dict(frame_sha256=digest,captured_at=frame.get('captured_at'),
                identity_version=frame.get('identity_version'),geometry_version=frame.get('geometry_version'))
    def text(record,path):
        if (not isinstance(record,dict) or record.get('status')!='observed' or not _score(record.get('confidence'),.97)
                or not isinstance(record.get('value'),str) or not record['value'].strip()
                or any(key in record and record[key]!=value for key,value in tokens.items())):
            gap(path);return None
        return record['value']
    for uid in selected:
        if uid not in ids:gap('selected_plan_not_observed:'+uid);continue
        raw=rows[ids.index(uid)];path='plans.'+uid
        name=text(raw.get('name'),path+'.name')
        if name is not None:names[uid]=name
        if raw.get('coverage')!='full':gap(path+'.complete_target_coverage')
        targets=raw.get('targets')
        if not isinstance(targets,list) or not 1<=len(targets)<=16:gap(path+'.targets');continue
        output=[]
        for index,target in enumerate(targets):
            target_path=path+'.targets.'+str(index)
            if not isinstance(target,dict):gap(target_path);continue
            hero=text(target.get('hero_id'),target_path+'.hero_id')
            # Count, role and priority are explicit planning choices. They do
            # not assert a default copy-merging rule or measured combat value.
            if target.get('role') not in ('core','transition'):gap(target_path+'.role')
            if type(target.get('count'))is not int or not 1<=target['count']<=8:gap(target_path+'.count_policy')
            if type(target.get('priority'))is not int or not 1<=target['priority']<=100:gap(target_path+'.priority_policy')
            lists={}
            for key in ('replaces','ban_tags'):
                value=target.get(key,[])
                if (not isinstance(value,list) or len(value)>16 or any(not isinstance(x,str)or not x for x in value)
                        or len(set(value))!=len(value)):
                    gap(target_path+'.'+key);value=[]
                lists[key]=value
            if hero is None:continue
            output.append(dict(hero_id=hero,role=target.get('role'),count=target.get('count'),
                               priority=target.get('priority'),replaces=lists['replaces'],
                               ban_tags=lists['ban_tags'],desired_star=target.get('desired_star'),
                               source=dict(kind='screen_recognition',reference='frame:'+str(digest)+'/'+uid+'/'+str(index))))
        plan=dict(lineup_id=uid,source=dict(kind='screen_recognition',reference='frame:'+str(digest)+'/'+uid),
                  targets=output,search_min_level=levels.get(uid))
        if 'chess_player_id' in raw:
            player=text(raw['chess_player_id'],path+'.chess_player_id')
            if player is not None:plan['chess_player_id']=player
        mapping=raw.get('ban_mapping_source')
        if mapping is not None:
            try:
                parsed=Source(**mapping)
                if parsed.kind!='reviewed_rule':raise ValueError('reviewed_mapping_required')
                plan['ban_mapping_source']=deepcopy(mapping)
            except (ValueError,TypeError):gap(path+'.reviewed_ban_mapping')
        elif any(target['ban_tags'] for target in output):gap(path+'.reviewed_ban_mapping')
        plans.append(plan)
    if gaps:return pending()
    try:
        Spending(spending['reference'],**{key:spending[key] for key in BUDGETS})
        for plan in plans:
            targets=tuple(Target(**dict(row,source=Source(**row['source']),replaces=tuple(row['replaces']),
                                         ban_tags=tuple(row['ban_tags']))) for row in plan['targets'])
            check=dict(plan,source=Source(**plan['source']),targets=targets)
            if 'ban_mapping_source' in check:check['ban_mapping_source']=Source(**check['ban_mapping_source'])
            Lineup(**check)
    except (KeyError,ValueError,TypeError) as error:
        gap('invalid_selected_policy:'+str(error));return pending()
    policy=dict(schema_version='v41-lineup-policy/1',recommendation_provider='in_game_lingbao',plans=plans,
                spending=deepcopy(spending),upgrades=[],unit_upgrade_semantics_verified=False,
                recommendation_selection=dict(reference=selection['reference'],plan_ids=list(selected),
                    catalog_frame=deepcopy(frame),display_names=names))
    return dict(status='ready',policy=policy,gaps=[],display_names=names,execution_allowed=False)
