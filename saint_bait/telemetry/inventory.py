"""Read-only keepnet inventory and visible, currently open market quotes."""
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import re
import struct
import uuid
from .collections import object_list


@dataclass(frozen=True)
class CorfFish:
    fish_id: str
    species: str
    weight_g: int
    grade: int
    caught_at: str | None
    caught_waterbody: str | None
    bait_id: str | None


def filetime_iso(value):
    try:
        stamp=(value-116444736000000000)/10_000_000
        result=datetime.fromtimestamp(stamp,timezone.utc)
        return result.isoformat() if 2020<=result.year<=2100 else None
    except (ValueError,OverflowError,OSError):return None


def silver_cents(text):
    if not isinstance(text,str):return None
    text=text.replace('\xa0','').replace(' ','').replace(',','.')
    if not re.fullmatch(r'\d{1,8}(?:\.\d{1,2})?',text):return None
    try:return int(Decimal(text)*100)
    except InvalidOperation:return None


class InventoryObserver:
    def __init__(self,observer):
        self.o=observer;self.r=observer.r
        self.player=next(c for c in observer.metadata.classes.values() if c['full_name']=='nnfmkefpbdi')
        self.smart=next(c for c in observer.metadata.classes.values() if c['full_name']=='RF4.Client.UI.RUISmartWidget')

    def root(self):
        f=next(f for f in self.o.metadata.all_fields(self.player) if f['name']=='<icaohegpknf>k__BackingField' and f['is_static'])
        return self.r.ptr(self.player['static_fields']+f['offset'])

    def fish(self,descriptor):
        if not descriptor or self.o.cls(descriptor)['full_name']!='lmeocpochih':return None
        species=self.o.string(descriptor,'gmafbfjkjpb')
        weight=self.o.integer(descriptor,'daknlhmlpbj')
        field=self.o.field(descriptor,'hcgnofefffh')
        if field['type']!='dohoaehalpj':raise ValueError('Unexpected fish grade')
        grade=struct.unpack('<i',self.r.read(descriptor+field['offset'],4))[0]
        guid=self.o.field(descriptor,'cahhdnicmbn')
        if guid['type']!='System.Guid':raise ValueError('Unexpected fish identity')
        fish_id=str(uuid.UUID(bytes_le=self.r.read(descriptor+guid['offset'],16)))
        time_field=self.o.field(descriptor,'dgnoilmagpc')
        if time_field['type']!='long':raise ValueError('Unexpected fish timestamp')
        caught_at=filetime_iso(struct.unpack('<q',self.r.read(descriptor+time_field['offset'],8))[0])
        if not species or not 1<=weight<=2000000 or not 0<=grade<=4:return None
        return CorfFish(fish_id,species,weight,grade,caught_at,self.o.string(descriptor,'dlfglmffeah'),
                        self.o.string(descriptor,'jnbeeajgopa'))

    def corf(self):
        root=self.root()
        if not root:return ()
        corf=self.o.ref(root,'<ddbcdaigpid>k__BackingField')
        items=self.o.ref(corf,'dnbnpcggipg') if corf else 0
        models=object_list(self.o,self.o.ref(items,'mkcacidbpbk'),4096) if items else ()
        container=self.o.ref(corf,'clhbanimoje') if corf else 0
        ids=set()
        if container:
            field=self.o.field(container,'aneifjkkipm')
            if self.o.metadata.type_info(field['type_data'])['name']!='System.Guid':raise ValueError('Unexpected keepnet identity array')
            array=self.r.ptr(container+field['offset'])
            count=self.r.ptr(array+24) if array else 0
            if not 0<=count<=500:raise ValueError('Keepnet outside bounds')
            ids={str(uuid.UUID(bytes_le=self.r.read(array+32+16*i,16))) for i in range(count)}
        rows=[]
        for model in models:
            if model and self.o.cls(model)['full_name']=='pgadiedjfkc':
                fish=self.fish(self.o.ref(model,'canpbkiogjm'))
                if fish and fish.fish_id in ids:rows.append(fish)
        if len(rows)>500:raise ValueError('Keepnet outside bounds')
        return tuple(rows)

    def market_open(self,controller):
        ui=self.o.ref(controller,'m_ui')
        dialogs=object_list(self.o,self.o.ref(ui,'efhiiendddm')) if ui else ()
        for dialog in dialogs:
            if self.o.cls(dialog)['full_name']!='RF4.Client.UI.Explorer.RUIExplorerDialog':continue
            container=self.o.ref(dialog,'nhlemnpfakn')
            active=self.o.ref(container,'imjhcejcidf') if container else 0
            if active and self.o.cls(active)['full_name']=='RF4.Client.UI.Explorer.RUIMarketExplorerPanel':return True
        return False

    def prices(self,controller,waterbody):
        if not waterbody or not self.market_open(controller):return ()
        f=next(f for f in self.o.metadata.all_fields(self.smart) if f['name']=='nihpbmlpljd' and f['is_static'])
        widgets=object_list(self.o,self.r.ptr(self.smart['static_fields']+f['offset']),4096)
        now=datetime.now(timezone.utc)
        rows=[]
        for cell in widgets:
            if not cell or self.o.cls(cell)['full_name']!='RF4.Client.UI.Explorer.RUIMarketOrganismCell':continue
            model=self.o.ref(cell,'nnghlepcnlf')
            fish=self.fish(self.o.ref(model,'canpbkiogjm')) if model else None
            if not fish:continue
            label=self.o.ref(cell,'m_price')
            cents=silver_cents(self.o.string(label,'mText')) if label else None
            label=self.o.ref(cell,'m_timestamp')
            text=self.o.string(label,'mText') if label else ''
            freshness=re.search(r'(\d{1,3})%',text or '')
            if cents is None or not freshness or not 0<=int(freshness[1])<=100:continue
            fresh=int(freshness[1])
            signature=f'{waterbody}:{fish.fish_id}:{cents}:{fresh}:{int(now.timestamp())//600}'
            rows.append(dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rf4-market:'+signature)),
                observed_at=now.isoformat(),waterbody_id=waterbody,fish_id=fish.fish_id,species=fish.species,
                weight_g=fish.weight_g,grade=fish.grade,freshness=fresh,price_cents=cents))
        return tuple(rows)
