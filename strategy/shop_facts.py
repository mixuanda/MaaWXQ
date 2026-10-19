"""Pure projection of existing hero-template/OCR and numeric recognizer results."""
import re


def integer(value):
    value=re.sub(r'\s+','',str(value))
    return int(value) if value.isdecimal() and len(value)<=3 else None


def recognize_offers(frame, values, lexicon, banks, *, factions=None, faction_source=None):
    factions=(factions or {}) if faction_source else {}
    values=(values.get('values',{}) if values.get('frame_sha256')==frame['sha256']
            and values.get('captured_at')==frame['captured_at'] else {})
    scores={x['name']:x['score'] for x in frame['matches']}; result=[]
    for slot in range(4):
        found=set()
        for bank,(_,entries) in enumerate(banks):
            for index,name in entries:
                if scores.get(f'hero_{slot}_{bank}_{index}',0)>=.97:found.add(name)
        ocr=re.sub(r'\s+','',str(values.get('name'+str(slot),'')))
        if ocr in lexicon:found.add(ocr)
        prices=frame.get('numbers',{}).get('prices',[])
        number=prices[slot] if isinstance(prices,list)and len(prices)>slot else {}
        name=next(iter(found)) if len(found)==1 else None
        result.append(dict(slot=slot,offer_id='shop:'+str(slot),name=name,name_candidates=sorted(found),raw_ocr=ocr,
            price=number.get('Value') if number.get('Known')is True and scores.get('price_'+str(slot),0)>=.97 else None,
            faction=factions.get(name),faction_source=faction_source if name in factions else None))
    return result
