"""Small synthetic choices; no asserted WXQ stats, odds or star recipe."""
from datetime import datetime, timezone, timedelta
import unittest

from strategy.advisor import Advisor
from strategy.contracts import Source
from strategy.lineup import Affinity, Lineup, Spending, Target, Upgrade


class LineupAdvisorTests(unittest.TestCase):
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = Source('synthetic', 'fixture-only:not-game-rules')

    def fields(self):
        values = dict(board_ids=('a', 'b', 'c', 'd'), hand_ids=(), offer_ids=('oe', 'junk'),
                      capacity=5, free_hand=3, credits=34, currency_id='fixture-energy', player_level=5,
                      refresh_cost=2, refresh_currency_id='fixture-energy', level_up_cost=8,
                      level_up_target_level=5, level_up_currency_id='fixture-energy',
                      talent_ids=('fixture-talent',), equipment_ids=('fixture-equipment',), faction_active=True)
        values.update({'hero:'+uid: uid.upper() for uid in 'abcd'})
        values.update({'hero:oe':'E', 'hero:junk':'X', 'price:oe':5, 'price:junk':1,
                       'currency:oe':'fixture-energy', 'currency:junk':'fixture-energy'})
        return values

    def advisor(self, values=None, bans=()):
        advisor = Advisor({'schema_version':'strategy-session/1', 'engine':'reviewed_rules',
                           'rule_data':{'schema_version':'1.0', 'domain':'gameplay','rules':[]}}, allow_test_rules=True)
        self.observe(advisor, 'start', {}, kind='match_start')
        self.observe(advisor, 'board', values if values is not None else self.fields())
        self.observe(advisor, 'bans', {'banned_tags':bans}, kind='bans')
        return advisor

    def observe(self, advisor, event_id, values, *, kind='state', seconds=0, **extra):
        at = self.at+timedelta(seconds=seconds)
        event = dict(schema_version='1.0', event_id=event_id, match_id='fixture-match', kind=kind,
                     observed_at=at.isoformat(), ingested_at=at.isoformat(), round=5, phase='preparation',
                     context_confidence=1, source={'kind':'synthetic','reference':'fixture-only:'+event_id},
                     fields=[{'key':key,'status':'observed','value':list(value) if isinstance(value,tuple) else value,
                              'confidence':1} for key,value in values.items()], **extra)
        advisor.observe(event, now=at)

    def plan(self, final='E', **extra):
        return Lineup('goal-'+final, self.source, tuple(Target(hero,self.source) for hero in 'ABCD'+final),
                      search_min_level=5, **extra)

    def spend(self, **extra):
        return Spending('fixture-policy:not-interest-or-odds', reserve=4, refresh_spend_cap=6,
                        refresh_count_cap=3, **extra)

    def test_goal_first_buys_needed_card_instead_of_cheapest_junk_and_deploys_owned_core(self):
        advisor = self.advisor(); result = advisor.advise_lineup([self.plan()], decision_at=self.at, spending=self.spend())
        self.assertEqual((result['action'],result['offer']['hero_id']), ('buy','E'))
        self.assertEqual(result['rejected_offers'][0]['reason'], 'not_needed_for_selected_lineup')
        values = self.fields(); del values['hero:junk']
        self.assertEqual(self.advisor(values).advise_lineup([self.plan()],decision_at=self.at,spending=self.spend())['action'],'buy')
        values = self.fields(); values['offer_ids']=('oe','of')
        values.update({'price:oe':100,'hero:of':'F','price:of':5,'currency:of':'fixture-energy'})
        result = self.advisor(values).advise_lineup([self.plan(),self.plan('F')],decision_at=self.at,spending=self.spend())
        self.assertEqual(result['selected_lineup'],'goal-F')
        values = self.fields(); values.update(hand_ids=('held-e',), offer_ids=('junk',)); values['hero:held-e']='E'
        result = self.advisor(values).advise_lineup([self.plan()], decision_at=self.at, spending=self.spend())
        self.assertEqual((result['action'],result['unit_id']), ('deploy','held-e'))
        self.assertFalse(result['execution_allowed'])

    def test_refresh_is_bounded_and_below_policy_level_uses_only_observed_upgrade_quote(self):
        values = self.fields(); values['offer_ids']=('junk',)
        result = self.advisor(values).advise_lineup([self.plan()], decision_at=self.at, spending=self.spend())
        self.assertEqual(result['action'],'refresh'); self.assertEqual(result['refresh_budget']['max_additional_refreshes'],3)
        self.assertIsNone(result['refresh_budget']['pool_probabilities'])
        values['player_level']=4
        # A fifth-quality card must not masquerade as player level five.
        values['quality_tier:junk']=5
        result = self.advisor(values).advise_lineup([self.plan()], decision_at=self.at, spending=self.spend())
        self.assertEqual((result['action'],result['target_player_level']),('level_up',5))
        del values['level_up_cost']
        self.assertEqual(self.advisor(values).advise_lineup([self.plan()],decision_at=self.at,spending=self.spend())['action'],'hold')
        values['player_level']=5
        self.assertEqual(self.advisor(values).advise_lineup([self.plan()],decision_at=self.at,
                         spending=self.spend(refresh_spent=6))['action'],'hold')

    def test_duplicate_priority_uses_explicit_star_recipe_and_never_card_quality(self):
        values = self.fields(); values.update(board_ids=('a','b','c','d','e'), hand_ids=('a2','a3'), offer_ids=('oa','junk'))
        values.update({'hero:e':'E','hero:a2':'A','hero:a3':'A','hero:oa':'A','price:oa':4,
                       'currency:oa':'fixture-energy','star:a':1,'star:a2':1,'star:a3':1,'star:oa':1,'quality_tier:oa':5})
        targets = (Target('A',self.source,desired_star=2),)+tuple(Target(h,self.source)for h in 'BCDE')
        plan = Lineup('fixture-upgrade',self.source,targets,search_min_level=5)
        # Four inputs here are declared solely for this synthetic fixture.
        rule = Upgrade('A',1,2,4,self.source)
        result = self.advisor(values).advise_lineup([plan],decision_at=self.at,spending=self.spend(),upgrades=(rule,))
        self.assertEqual(result['action'],'buy'); self.assertTrue(result['offer']['completes_upgrade'])
        result = self.advisor(values).advise_lineup([plan],decision_at=self.at,spending=self.spend())
        self.assertEqual(result['action'],'hold'); self.assertIn('upgrade_rule_unknown:A',result['unknowns'])

    def test_match_ban_survives_later_empty_report_and_transition_names_its_replacement(self):
        values = self.fields(); values.update(offer_ids=('of','oe')); values.update({'hero:of':'F','price:of':7,'currency:of':'fixture-energy'})
        blocked = Lineup('blocked',self.source,tuple(Target(h,self.source,ban_tags=('blocked-tag',)if h=='E'else())for h in 'ABCDE'),search_min_level=5,ban_mapping_source=self.source)
        advisor = self.advisor(values,bans=('blocked-tag',)); self.observe(advisor,'later-empty-ban',{'banned_tags':()},kind='bans',seconds=.1)
        result = advisor.advise_lineup([blocked,self.plan('F',ban_mapping_source=self.source)],decision_at=self.at+timedelta(seconds=.1),spending=self.spend())
        self.assertEqual(result['selected_lineup'],'goal-F'); self.assertEqual(result['offer']['hero_id'],'F')
        values = self.fields(); values.update(hand_ids=('temp',),offer_ids=('junk',)); values['hero:temp']='T'
        plan = self.plan(); plan = Lineup('explicit-transition',self.source,plan.targets+(Target('T',self.source,role='transition',replaces=('E',)),),search_min_level=5)
        result = self.advisor(values).advise_lineup([plan],decision_at=self.at,spending=self.spend())
        self.assertEqual((result['action'],result['hero_id'],result['replaces']),('deploy','T',['E']))

    def test_sourced_talent_equipment_faction_and_opponent_fit_uses_board_origin_not_new_note(self):
        values = self.fields(); values['offer_ids']=('oe','of'); values.update({'hero:of':'F','price:of':5,'currency:of':'fixture-energy'})
        link = Affinity('fixture-link',self.source,(('self.talent_ids','fixture-talent'),
            ('self.equipment_ids','fixture-equipment'),('self.faction_active',True),('opponent.hero_ids','observed-counter')),('F',),2)
        plans = [self.plan(),self.plan('F',affinities=(link,))]; advisor = self.advisor(values)
        self.observe(advisor,'opponent-board',{'hero_ids':('observed-counter',)},kind='opponent',opponent_id='opponent-1',coverage='partial')
        result = advisor.advise_lineup(plans,decision_at=self.at,spending=self.spend(),opponent_id='opponent-1')
        self.assertEqual(result['selected_lineup'],'goal-F'); self.assertFalse(result['opponent_snapshots'][0]['unseen_units_absent'])
        self.observe(advisor,'fresh-own',values,seconds=31)
        self.observe(advisor,'note-only',{'note':'not a new board'},kind='opponent',seconds=31,opponent_id='opponent-1')
        result = advisor.advise_lineup(plans,decision_at=self.at+timedelta(seconds=31),spending=self.spend(),opponent_id='opponent-1')
        self.assertEqual(result['selected_lineup'],'goal-E'); self.assertFalse(result['opponent_snapshots'][0]['usable'])
        self.assertEqual(result['opponent_snapshots'][0]['event_id'],'opponent-board')


if __name__=='__main__': unittest.main()
