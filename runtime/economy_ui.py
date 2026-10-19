"""Read action labels/quotes from a reviewed layout on the current frame.

The initial profile recognizes the saved free-refresh layout. Player-level and
resulting-level ROIs are intentionally absent until their real UI is inspected.
"""
import hashlib
import json
from pathlib import Path
import re
from runtime.surface_gate import _score


def compact(value):
    return re.sub(r'\s+','',str(value))


class EconomyUI:
    def __init__(self, path):
        self.profile=json.loads(Path(path).read_text(encoding='utf-8'))
        if self.profile.get('schema_version')!='v41-economy-ui/1':
            raise ValueError('economy_UI_profile_schema_unknown')
        for row in self.profile['anchors']:
            if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('economy_UI_reference_changed')
        mapping=self.profile.get('currency_mapping',{})
        proof=mapping.get('source',{})
        if mapping.get('verified')is True:
            if hashlib.sha256(Path(proof['path']).read_bytes()).hexdigest()!=proof['sha256']:
                raise ValueError('verified_currency_mapping_source_changed')
        self.regions=dict(self.profile['regions'])
        for key,reader in self.profile.get('scalar_readers',{}).items():
            if key not in ('player_level','level_up_target_level') or not reader.get('semantic_source'):
                raise ValueError('reviewed_player_level_semantics_required')
            self.regions[key]=reader['rect']
        for key, reader in self.profile.get('quote_readers', {}).items():
            if key not in ('refresh_cost', 'level_up_cost') or not reader.get('semantic_source'):
                raise ValueError('reviewed_current_quote_semantics_required')
            if 'value' not in re.compile(reader['pattern']).groupindex:
                raise ValueError('explicit_quote_value_capture_required')
            self.regions[reader['text_key']] = reader['rect']

    def anchors(self):
        return [{key:row[key] for key in ('id','path','rect')} for row in self.profile['anchors']]

    def parse(self, frame, text):
        if (text.get('frame_sha256')!=frame['sha256'] or text.get('captured_at')!=frame['captured_at']
                or not isinstance(text.get('values'),dict)):
            return {'actions':{},'reason':'current_OCR_frame_binding_required'}
        text=text['values']
        anchors=frame.get('v14',{}).get('anchors',[])
        if (any(not isinstance(row,dict)or not isinstance(row.get('id'),str)or not _score(row.get('score'))for row in anchors)
                or len({row['id']for row in anchors})!=len(anchors)):
            return {'actions':{},'reason':'unique_current_economy_anchors_required'}
        scores={x['id']:x['score'] for x in frame.get('v14',{}).get('anchors',[])}
        identity=frame.get('identity',{}).get('identity_version')
        shared=dict(status='observed',confidence=.97,frame_sha256=frame['sha256'],identity_version=identity,
                    geometry_version=frame['identity'].get('geometry_version'))
        out={'actions':{},'raw_text':dict(text),'reference':self.profile['reference']}
        for key,reader in self.profile.get('scalar_readers',{}).items():
            value=compact(text.get(key,''))
            # The reviewed ROI/semantic source identifies PLAYER level. Ratios,
            # hero level, card tier and the upgrade cost do not match a scalar.
            match = re.fullmatch(reader.get('pattern', r'(?P<value>\d{1,2})'), value)
            if (scores.get(reader['anchor_id'],0)>=.97 and match and 'value' in match.re.groupindex
                    and re.fullmatch(r'\d{1,2}', match['value']) and 1 <= int(match['value']) <= 99):
                out[key]=dict(shared,value=int(match['value']),semantic_source=reader['semantic_source'])
        quotes = {}
        for key, reader in self.profile.get('quote_readers', {}).items():
            match = re.fullmatch(reader['pattern'], compact(text.get(reader['text_key'], '')))
            if (scores.get(reader['anchor_id'], 0) >= .97 and match
                    and re.fullmatch(r'\d{1,3}', match['value'])):
                quotes[key] = dict(shared, value=int(match['value']), semantic_source=reader['semantic_source'])
        def enabled(name):
            button = self.profile.get('actions', {}).get(name, {})
            anchor = button.get('enabled_anchor_id')
            return button if anchor and scores.get(anchor, 0) >= .97 else None
        def bind(button):
            return dict(shared, rect=button['rect'], target=button['target'], label_verified=True, enabled_verified=True)
        free=compact(text.get('refresh_label',''))=='免费刷新'
        count=re.fullmatch(r'[xX×*]?(\d{1,2})',compact(text.get('refresh_counter','')))
        if free and scores.get('economy_free_refresh_label',0)>=.97:
            out['refresh_cost']=dict(shared,value=0,semantic_source='current literal 免费刷新')
            if count and int(count[1])>0:
                button=self.profile['actions']['free_refresh']
                out['actions']['refresh']=dict(shared,rect=button['rect'],target=button['target'],
                    label_verified=True,enabled_verified=True,remaining_free_refreshes=int(count[1]))
        # Paid refresh is supported only by an explicitly reviewed CURRENT
        # price reader plus an enabled-state anchor, never a built-in price.
        if not free and 'refresh_cost' in quotes and quotes['refresh_cost']['value'] > 0:
            out['refresh_cost'] = quotes['refresh_cost']
            button = enabled('paid_refresh')
            if button: out['actions']['refresh'] = bind(button)
        # The number beside 升级 is its visible quote, not the current/next level.
        upgrade=re.fullmatch(r'(\d{1,3})升级',compact(text.get('upgrade_button','')))
        if upgrade and scores.get('economy_upgrade_label',0)>=.97:
            out['level_up_cost']=dict(shared,value=int(upgrade[1]),semantic_source='current upgrade button cost')
            if all(key in out for key in ('player_level','level_up_target_level')):
                button=enabled('level_up')
                if button: out['actions']['level_up']=bind(button)
        if 'level_up_cost' in quotes:
            if 'level_up_cost' in out and out['level_up_cost']['value'] != quotes['level_up_cost']['value']:
                out.pop('level_up_cost'); out['actions'].pop('level_up', None)
                out['reason'] = 'conflicting_current_upgrade_quotes'
            else:
                out['level_up_cost'] = quotes['level_up_cost']
                button = enabled('level_up')
                if (button and 'player_level' in out and 'level_up_target_level' in out
                        and out['level_up_target_level']['value'] > out['player_level']['value']):
                    out['actions']['level_up'] = bind(button)
        return out
