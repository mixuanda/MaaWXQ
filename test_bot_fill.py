import copy,unittest
from runtime.bot_fill import recognize,decide,verify_step
def frame():
    matches=[{'name':'lobby_title','score':1,'center':[1,1]}]
    for i in range(1,6):
        for kind in ('empty','bot_avatar','bot_label','operation','robot_menu'):
            score=int((i==1 and kind in ('bot_avatar','bot_label')) or (i>1 and kind in ('empty','operation')))
            matches.append({'name':'slot_'+str(i)+'_'+kind,'score':score,'center':[i,10]})
    return {'matches':matches,'sha256':'a'*64}
class BotFillTests(unittest.TestCase):
    def test_unknown_occupied_slot_blocks_all_input(self):
        source=frame();self.assertEqual(decide(recognize(source))['slot'],2)
        next(x for x in source['matches'] if x['name']=='slot_5_empty')['score']=0
        self.assertEqual(decide(recognize(source))['action'],'stop')
    def test_menu_must_be_for_first_verified_empty_slot(self):
        source=frame();next(x for x in source['matches'] if x['name']=='slot_3_robot_menu')['score']=1
        self.assertEqual(decide(recognize(source))['reason'],'unexpected_slot_menu')
        next(x for x in source['matches'] if x['name']=='slot_3_robot_menu')['score']=0
        next(x for x in source['matches'] if x['name']=='slot_2_robot_menu')['score']=1
        self.assertEqual(decide(recognize(source))['operation'],'add_room_bot')
    def test_added_bot_requires_target_and_unchanged_other_slots(self):
        before=recognize(frame());decision={'slot':2,'operation':'add_room_bot'};after=copy.deepcopy(before)
        after['slots'][1]['kind']='bot';after['bot_count']=2
        self.assertTrue(verify_step(before,decision,after))
        after['slots'][4]['kind']='bot';self.assertFalse(verify_step(before,decision,after))
if __name__=='__main__':unittest.main()
