"""Bounded observations of actual scene rods. No injection, calls or writes."""
import struct
import math
from dataclasses import dataclass
from ..rods import RodView, classify_memory
from .reader import Metadata
from .transforms import world_position
from .equipment import EquipmentReader


@dataclass(frozen=True)
class TackleMetrics:
    code: int
    line: float
    current: float | None
    limit: float | None
    drag: float | None
    setting: int | None
    locked: bool | None

    @property
    def fraction(self):
        return self.current/self.limit if self.current is not None and self.limit else None


class TackleObserver:
    def __init__(self, reader):
        self.r = reader
        self.metadata = Metadata(reader)
        self.scene_identity = None
        self.game_controller = None
        self.equipment=EquipmentReader(self)
        self.controller = next(c for c in self.metadata.classes.values()
                               if c['full_name'] == 'RF4.Client.GameController')

    def cls(self, obj):
        return self.metadata.describe_class(self.r.ptr(obj))

    def field(self, obj, name):
        return next(f for f in self.metadata.all_fields(self.cls(obj))
                    if f['name'] == name and not f['is_static'] and f['offset'] >= 16)

    def ref(self, obj, name):
        field = self.field(obj, name)
        if field['type_code'] not in (18,21,28):
            raise ValueError('Unexpected reference layout')
        return self.r.ptr(obj+field['offset'])

    def integer(self, obj, name, protected=False):
        field = self.field(obj,name)
        if protected:
            if field['type'] != 'ppbonkceloo':
                raise ValueError('Unexpected protected weight layout')
            encoded,key,_ = struct.unpack('<III',self.r.read(obj+field['offset'],12))
            return struct.unpack('<i',struct.pack('<I',encoded^key))[0] if key else None
        if field['type_code'] != 8:
            raise ValueError('Unexpected integer layout')
        return struct.unpack('<i',self.r.read(obj+field['offset'],4))[0]

    def string(self, obj, name):
        field = self.field(obj,name)
        if field['type_code'] != 14:
            raise ValueError('Unexpected species string layout')
        text = self.r.ptr(obj+field['offset'])
        if not text:
            return None
        size = struct.unpack('<i',self.r.read(text+16,4))[0]
        if not 0 <= size <= 128:
            raise ValueError('Species identifier outside bounds')
        return self.r.read(text+20,size*2).decode('utf-16-le') if size else ''

    def number(self, obj, name):
        field = self.field(obj,name)
        fmt = {12:'<f',13:'<d'}.get(field['type_code'])
        if fmt is None:
            raise ValueError('Unexpected metric type')
        value = struct.unpack(fmt,self.r.read(obj+field['offset'],struct.calcsize(fmt)))[0]
        if not math.isfinite(value):
            raise ValueError('Non-finite tackle metric')
        return value

    def metrics(self,tackle):
        phase_field = self.field(tackle,'opmmalbglpl')
        if phase_field['type']!='kieibhlheed' or phase_field['type_code']!=17:
            raise ValueError('Unexpected fishing phase enum')
        code = struct.unpack('<i',self.r.read(tackle+phase_field['offset'],4))[0]
        if code not in (0,1,2,3):
            raise ValueError('Unknown fishing phase')
        connector = self.ref(tackle,'imdaclihign')
        if not connector or self.cls(connector)['full_name']!='RF4.Client.FishingScene.RigConnector':
            raise ValueError('Line connector unavailable')
        # Same getter as RUIReelCounterIndicator: interface slot 42 ->
        # RodRigFishingSet.ejldhgkfjlc (0x1157D80) -> connector + 128.
        line = self.number(connector,'pkpijfjceof')
        if not 0<=line<=10000:
            raise ValueError('Line length outside bounds')
        # RUILoadIndicator.Update (0x125D190) divides interface slot 3
        # by slot 6. Verified getters: fcpagkkekeb.koomajjcigp / jbheonnnbhe.
        force = self.ref(tackle,'fcpagkkekeb')
        current,limit = None,None
        if force and self.cls(force)['full_name']=='ihlkhcenhfc':
            current = self.number(force,'koomajjcigp')
            limit = self.number(tackle,'jbheonnnbhe')
            if not (0<=current<=1e9 and 0<limit<=1e9 and current/limit<=1000):
                raise ValueError('Load ratio outside bounds')
        drag,setting,locked = self.brake(tackle)
        return TackleMetrics(code,line,current,limit,drag,setting,locked)

    def brake(self,tackle):
        names = {f['name'] for f in self.metadata.all_fields(self.cls(tackle))}
        if 'mdokjmcfnch' not in names:
            return None,None,None
        reel = self.ref(tackle,'mdokjmcfnch')
        if not reel or self.cls(reel)['full_name']!='RF4.Client.FishingScene.Reel':
            raise ValueError('Reel unavailable')
        model = self.ref(reel,'<nfjcgaalamm>k__BackingField')
        if not model or self.cls(model)['full_name']!='lkgakdhinig':
            raise ValueError('Reel model unavailable')
        step = self.integer(model,'<hgdidnmkkli>k__BackingField')
        if step is None or not 0<=step<=29:
            raise ValueError('Unknown brake setting')
        # RUIReelFrictionIndicator displays step+1. Model.mclbpbanebo
        # (0x955E40) writes the current force, including settings and wear.
        force = self.number(model,'<bmpepnpmjho>k__BackingField')
        heat = self.number(reel,'mmoiekbpoam')
        if step!=self.integer(model,'<hgdidnmkkli>k__BackingField'):
            raise ValueError('Brake changed during read')
        if step==29:
            if force<1e30:
                raise ValueError('Locked brake force inconsistent')
            return None,30,True
        if not 0<force<=1e9:
            raise ValueError('Brake force outside bounds')
        # Same effective-force getter used by the reel physics: kabahnodibh,
        # RVA 0xA7B670. A locked brake is a sentinel, not a huge real limit.
        drag = ((1-min(1.,max(0.,heat)))*.05+.95)*force
        return drag,step+1,False

    def read(self):
        self.scene_identity = None
        obj = self.r.ptr(self.controller['static_fields'])
        if not obj or self.r.ptr(obj) != self.controller['address']:
            raise ValueError('Fishing scene unavailable')
        self.game_controller = obj
        for name in ('m_levelLoader','okjdbiempch','pcmhlbhlhdl'):
            obj = self.ref(obj,name)
            if not obj:
                return ()
        active = self.ref(obj,'jfmipmgioae')
        self.scene_identity = obj
        player_position=world_position(self.r,self.ref(obj,'cicmhgacljm'))
        items = self.ref(obj,'ncjnbngjkmg')
        tackles = []
        version = None
        if items:
            count = self.integer(items,'_size')
            if not 0 <= count <= 16:
                raise ValueError('Fishing set count outside bounds')
            version_address = items+self.field(items,'_version')['offset']
            version = self.r.read(version_address,4)
            field = self.field(items,'_items')
            if field['type_code'] != 29:
                raise ValueError('Unexpected fishing set array layout')
            array = self.r.ptr(items+field['offset'])
            if count and (not array or self.r.ptr(array+24) < count):
                raise ValueError('Invalid fishing set array')
            tackles = [self.r.ptr(array+32+i*8) for i in range(count)]
        if active and active not in tackles:
            tackles.append(active)
        result = []
        for tackle in dict.fromkeys(tackles):
            name = self.cls(tackle)['full_name']
            if name not in ('RF4.Client.FishingScene.RodRigFishingSet','RF4.Client.FishingScene.RodReelRigFishingSet'):
                continue
            rig = self.ref(tackle,'bgjdabgkbla')
            if not rig:
                continue
            kind = self.cls(rig)['name']
            if kind.endswith(('Marker','FeedRocket')):
                continue
            kind = ('feeder' if kind.startswith('RigBottom') else
                    'float' if kind.startswith('RigBobber') else 'spinning')
            present = {f['name'] for f in self.metadata.all_fields(self.cls(rig))}
            fish, attached = None, False
            if 'jcaicghmlon' in present:
                hook = self.ref(rig,'jcaicghmlon')
                if hook:
                    fish = self.ref(hook,'<plilmmejlbo>k__BackingField')
                    attached = bool(self.ref(hook,'bbfnjddmlji'))
            species, weight, grade = None, None, None
            fish_distance=None
            confirmed = False
            if fish and attached and self.cls(fish)['full_name'] == 'RF4.Client.FishingScene.Fish':
                confirmed = self.ref(fish,'<nidcmfmejjm>k__BackingField') == tackle
                if confirmed and player_position is not None:
                    fish_position=world_position(self.r,self.ref(fish,'cicmhgacljm'))
                    if fish_position is not None:fish_distance=math.dist(player_position,fish_position)
                model = self.ref(fish,'coffdfkgfaa')
                if confirmed and model and self.cls(model)['full_name'] == 'nmhcohgdjon':
                    descriptor = self.ref(model,'nbhppkkldpm')
                    parameters = self.ref(model,'ejpfdimbeoj')
                    if descriptor and parameters:
                        species = self.string(descriptor,'nhjofmmmngl')
                        raw = self.integer(descriptor,'daknlhmlpbj')
                        copied = self.integer(parameters,'daknlhmlpbj',True)
                        if raw == copied and isinstance(raw,int) and 1 <= raw <= 2_000_000:
                            weight = raw
                        # nmhcohgdjon.mfiapcpkmkm (0xE26020) decodes the
                        # protected category. Trophy UI uses 3 / 4 for its
                        # ordinary / super-trophy marks (0xF02EE0).
                        category=self.field(descriptor,'hpjeeckiokf')
                        if category['type']=='dohoaehalpj' and category['type_code']==17:
                            raw_grade=struct.unpack('<i',self.r.read(descriptor+category['offset'],4))[0]
                            copied_grade=self.integer(parameters,'mpfleheflce',True)
                            if raw_grade==copied_grade and 0<=raw_grade<=4:grade=raw_grade
            on_rest = bool(self.ref(tackle,'phjkbmcbmim'))
            pending = bool(self.ref(tackle,'moabncmfjej'))
            metrics = self.metrics(tackle)
            rig_model=self.ref(rig,'coffdfkgfaa')
            clip=self.integer(rig_model,'<kjgcdannjhf>k__BackingField') if rig_model else None
            if clip is not None and not 0<=clip<=10000:
                raise ValueError('Clip length outside bounds')
            phase,cast = classify_memory(code=metrics.code,pending=pending,hooked=confirmed,
                                         active=tackle==active,on_rest=on_rest)
            result.append(RodView(identity=hex(tackle),kind=kind,active=tackle==active,
                                  on_rest=on_rest,hooked=confirmed,species=species,weight_g=weight,
                                  phase=phase,cast=cast,memory_metrics=True,state_code=metrics.code,
                                  line_m=metrics.line,load_fraction=metrics.fraction,
                                  load_force=metrics.current,tackle_limit=metrics.limit,
                                  drag_force=metrics.drag,drag_setting=metrics.setting,
                                  drag_locked=metrics.locked,clip_m=clip,grade=grade,fish_distance=fish_distance,
                                  equipment=self.equipment.read(tackle,rig)))
        if version is not None and version != self.r.read(version_address,4):
            raise ValueError('Fishing set list changed during read')
        return tuple(result)
