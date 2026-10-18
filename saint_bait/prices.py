"""Conservative empirical estimates; never presented as a guaranteed sale."""
from datetime import datetime,timezone,timedelta
from statistics import median


def estimate_price(fish,market,samples,now=None):
    now=now or datetime.now(timezone.utc)
    def date(value):
        try:return datetime.fromisoformat(value)
        except (TypeError,ValueError):return None
    unique={}
    for sample in samples:
        observed=date(sample.get('observed_at'))
        if not observed or observed.tzinfo is None or not timedelta(0)<=now-observed<=timedelta(hours=24):continue
        if sample.get('waterbody_id')!=market or sample.get('species')!=fish.species or sample.get('grade')!=fish.grade:continue
        if type(sample.get('freshness')) is not int or not 0<=sample['freshness']<=100:continue
        weight=sample.get('weight_g');price=sample.get('price_cents')
        if type(weight) is not int or not 0<weight<=2000000 or type(price) is not int or price<0:continue
        key=sample.get('fish_id') or sample.get('id')
        if key not in unique or observed>date(unique[key]['observed_at']):unique[key]=sample
    samples=list(unique.values())
    exact=next((x for x in samples if fish.fish_id and x.get('fish_id')==fish.fish_id and now-date(x['observed_at'])<=timedelta(minutes=1)),None)
    if exact:return {'cents':exact['price_cents'],'samples':1,'observed_at':exact['observed_at'],'exact':True}
    caught=date(fish.caught_at)
    if not caught or caught.tzinfo is None or now<caught:return None
    freshness=round(max(0,1-(now-caught).total_seconds()/86400)*100)
    comparable=[x for x in samples if abs(x['weight_g']-fish.weight_g)<=fish.weight_g*.25
                and ((freshness==0 and x['freshness']==0) or
                     (freshness>0 and x['freshness']>0 and abs(freshness-x['freshness'])<=5))]
    if len(comparable)<3:return None
    rates=[x['price_cents']/x['weight_g'] for x in comparable]
    rate=median(rates)
    if rate<=0 or max(abs(x-rate)/rate for x in rates)>.2:return None
    return {'cents':round(rate*fish.weight_g),'samples':len(comparable),
            'observed_at':max(x['observed_at'] for x in comparable),'exact':False}
