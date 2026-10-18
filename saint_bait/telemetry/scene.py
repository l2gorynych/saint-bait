"""Bounded game bindings and modal state; no input or game method invocation."""
import struct
import math
from dataclasses import dataclass
from ..bindings import resolve_bindings,unity_key
from .transforms import world_pose,view_angles
from ..keepnet import parse_keepnet
from .collections import object_list
from .location import read_location
from .inventory import InventoryObserver


@dataclass(frozen=True)
class SceneView:
    bindings: tuple = ()
    dialogs: tuple = ()
    catch_id: str | None = None
    catch_ready: bool = False
    keep_key: str | None = None
    release_key: str | None = None
    net_present: bool = False
    net_catching: bool = False
    camera_id: str | None = None
    camera_angles: tuple | None = None
    satiety: float | None = None
    energy: float | None = None
    catch_species: str | None = None
    catch_weight_g: int | None = None
    catch_grade: int | None = None
    keepnet_count: int | None = None
    keepnet_capacity: int | None = None
    waterbody_id: str | None = None
    coordinates: tuple | None = None
    catch_fish_id: str | None = None
    catch_bait_id: str | None = None
    catch_origin: str | None = None
    catch_time: str | None = None


class SceneObserver:
    def __init__(self,observer):
        self.o=observer
        self.r=observer.r
        self.default_class=next(c for c in observer.metadata.classes.values() if c['full_name']=='iokfjdnnege')
        self.player_class=next(c for c in observer.metadata.classes.values() if c['full_name']=='nnfmkefpbdi')
        self.hud_class=next((c for c in observer.metadata.classes.values()
                             if c['full_name']=='RF4.Client.UI.HUD.RHUDWidget'),None)
        self.inventory=InventoryObserver(observer)

    def hud_widgets(self):
        if self.hud_class is None:return ()
        field=next(f for f in self.o.metadata.all_fields(self.hud_class)
                   if f['name']=='jhljoopjflf' and f['is_static'])
        return self.objects(self.r.ptr(self.hud_class['static_fields']+field['offset']),128)

    def keepnet(self,widgets=None):
        values=[]
        for widget in self.hud_widgets() if widgets is None else widgets:
            if widget and self.o.cls(widget)['full_name']=='RF4.Client.UI.HUD.RHUDPlayerCorfWidget':
                # Native UILabel text, the exact count/capacity shown by RF4.
                # Never retain the last value when the scene disappears.
                label=self.o.ref(widget,'_infoLabel')
                if label:
                    value=parse_keepnet(self.o.string(label,'mText'))
                    if value[0] is not None:values.append(value)
        return values[0] if len(values)==1 else (None,None)

    def nutrition(self):
        # Same source as RHUDPlayerParamsWidget.jfjfdhdmmkn (0x51B570):
        # nnfmkefpbdi.icaohegpknf -> profile -> canpbkiogjm.
        field=next(f for f in self.o.metadata.all_fields(self.player_class)
                   if f['name']=='<icaohegpknf>k__BackingField' and f['is_static'])
        if field['type']!='hncnmlgnhjm':raise ValueError('Player root layout changed')
        root=self.r.ptr(self.player_class['static_fields']+field['offset'])
        if not root:return None,None
        profile=self.o.ref(root,'<ffgmlajonoj>k__BackingField')
        params=self.o.ref(profile,'canpbkiogjm') if profile else 0
        if not params:return None,None
        if self.o.cls(params)['full_name']!='pmdcpeegbbd':raise ValueError('Player parameters changed')
        satiety=self.o.number(params,'odmpgbjjlnc')
        energy=self.o.number(params,'odbiihjlfop')
        if not (0<=satiety<=1.001 and 0<=energy<=1.001):raise ValueError('Nutrition outside bounds')
        return min(1.,satiety),min(1.,energy)

    def enum(self,obj,name,type_name):
        field=self.o.field(obj,name)
        if field['type']!=type_name or field['type_code']!=17:
            raise ValueError('Unexpected enum '+name)
        return struct.unpack('<i',self.r.read(obj+field['offset'],4))[0]

    def boolean(self,obj,name):
        field=self.o.field(obj,name)
        if field['type_code']!=2:
            raise ValueError('Unexpected boolean '+name)
        return bool(self.r.read(obj+field['offset'],1)[0])

    def objects(self,items,maximum=32):
        return object_list(self.o,items,maximum)

    def dictionary(self,table,modifiers=None):
        if not table:return {}
        count=self.o.integer(table,'_count')
        if not 0<=count<=256:raise ValueError('Binding count outside bounds')
        version=self.r.read(table+self.o.field(table,'_version')['offset'],4)
        array=self.r.ptr(table+self.o.field(table,'_entries')['offset'])
        if not array:
            if count:raise ValueError('Binding array absent')
            return {}
        if self.r.ptr(array+24)<count:raise ValueError('Binding array truncated')
        entry=self.o.metadata.describe_class(self.r.ptr(self.r.ptr(array)+64))
        fields={f['name']:f for f in self.o.metadata.all_fields(entry)}
        expected={'hashCode':16,'next':20,'key':24,'value':32}
        if any(name not in fields or fields[name]['offset']!=offset for name,offset in expected.items()):
            raise ValueError('Binding entry layout changed')
        if fields['key']['type']!='RF4.Client.UserInput.InputActionType' or fields['value']['type']!='RF4.Client.UserInput.InputPair':
            raise ValueError('Unexpected binding dictionary')
        result={}
        for index in range(count):
            hashed,_,action,_,pair=struct.unpack('<iiiIQ',self.r.read(array+32+24*index,24))
            if hashed<0:continue
            if not pair or self.o.cls(pair)['full_name']!='RF4.Client.UserInput.InputPair':raise ValueError('Invalid binding pair')
            codes=[]
            for name in ('<njdkhmohmfk>k__BackingField','<adekggpbojb>k__BackingField'):
                unit=self.o.ref(pair,name)
                codes.append(self.enum(unit,'<cejgmebgpln>k__BackingField','UnityEngine.KeyCode') if unit else 0)
            result[action]=tuple(codes)
            if modifiers is not None:
                modifier=self.enum(pair,'hekmcdjbpli','imchklbljbl')
                if modifier not in range(6):raise ValueError('Unknown input modifier')
                modifiers[action]=modifier
        if version!=self.r.read(table+self.o.field(table,'_version')['offset'],4):raise ValueError('Bindings changed during read')
        return result

    def read(self,controller,fisher):
        camera=self.o.ref(fisher,'m_cameraController')
        angles=None
        if camera and self.o.cls(camera)['full_name']=='RF4.Client.FishingScene.FisherCameraController':
            # The controller's dfnfmgdccnk angles are relative to the fisher
            # and may reset when changing rods. Preserve the world view instead.
            pose=world_pose(self.r,self.o.ref(camera,'cicmhgacljm'))
            if pose is not None:angles=view_angles(pose[1])
        manager=self.o.ref(camera,'dhfmgieampn') if camera else 0
        if not manager or self.o.cls(manager)['full_name']!='iokfjdnnege':raise ValueError('Game bindings unavailable')
        modifiers={}
        defaults=self.dictionary(self.r.ptr(self.default_class['static_fields']),modifiers)
        overrides=self.dictionary(self.o.ref(manager,'ddcgncdfpbg'),modifiers)
        ui=self.o.ref(controller,'m_ui')
        dialogs=self.objects(self.o.ref(ui,'efhiiendddm')) if ui else ()
        names=tuple(self.o.cls(obj)['full_name'] for obj in dialogs if obj)
        catch=next((obj for obj in dialogs if obj and self.o.cls(obj)['full_name']=='RF4.Client.UI.GameResult.RUIGameResultDialog'),0)
        ready=False
        keep,release=None,None
        catch_species,catch_weight,catch_grade=None,None,None
        catch_info=None
        if catch:
            widget=self.o.ref(catch,'m_widget')
            model=self.o.ref(widget,'nnghlepcnlf') if widget else 0
            if model and self.o.cls(model)['full_name']=='blehdkolhfl':
                item=self.o.ref(model,'<adfagfjailh>k__BackingField')
                if item and self.o.cls(item)['full_name']=='lmeocpochih':
                    catch_info=self.inventory.fish(item)
                    species=self.o.string(item,'gmafbfjkjpb')
                    weight=self.o.integer(item,'daknlhmlpbj')
                    grade=self.enum(item,'hcgnofefffh','dohoaehalpj')
                    if species and 1<=weight<=2_000_000 and 0<=grade<=4:
                        catch_species,catch_weight,catch_grade=species,weight,grade
            footer=self.o.ref(widget,'m_footer') if widget else 0
            if footer:
                ok=self.o.ref(footer,'m_btnOk')
                cancel=self.o.ref(footer,'m_btnCancel')
                keep=unity_key(self.enum(ok,'key','UnityEngine.KeyCode')) if ok else None
                release=unity_key(self.enum(cancel,'key','UnityEngine.KeyCode')) if cancel else None
                ready=(self.boolean(footer,'nnhgjblcfnp') and
                       (self.boolean(footer,'giefmfcfial') or self.boolean(footer,'chkmknjnppn')))
        net=self.o.ref(fisher,'kklcnangfcg')
        present=bool(net and self.o.cls(net)['full_name']=='RF4.Client.FishingScene.FishNet' and self.r.ptr(net+16))
        satiety,energy=self.nutrition()
        widgets=self.hud_widgets()
        keepnet_count,keepnet_capacity=self.keepnet(widgets)
        waterbody_id,coordinates=read_location(self.o,controller,widgets)
        return SceneView(bindings=resolve_bindings(defaults,overrides,modifiers),dialogs=names,
                         catch_id=hex(catch) if catch else None,catch_ready=ready,
                         keep_key=keep,release_key=release,net_present=present,
                         net_catching=present and self.boolean(net,'dmfklboogao'),
                         camera_id=hex(camera) if angles is not None else None,camera_angles=angles,
                         satiety=satiety,energy=energy,catch_species=catch_species,
                         catch_weight_g=catch_weight,catch_grade=catch_grade,
                         keepnet_count=keepnet_count,keepnet_capacity=keepnet_capacity,
                         waterbody_id=waterbody_id,coordinates=coordinates,
                         catch_fish_id=catch_info.fish_id if catch_info else None,
                         catch_bait_id=catch_info.bait_id if catch_info else None,
                         catch_origin=catch_info.caught_waterbody if catch_info else None,
                         catch_time=catch_info.caught_at if catch_info else None)
