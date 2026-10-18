"""Optional equipment presentation data; never used for fishing decisions."""
from dataclasses import dataclass
import re
from .collections import object_list


@dataclass(frozen=True)
class EquipmentItem:
    kind: str
    system_id: str
    brand: str | None = None
    condition: float | None = None
    strength_kg: float | None = None
    nominal_kg: float | None = None
    quantity: int | None = None
    length_m: float | None = None
    diameter_mm: float | None = None
    mass_g: float | None = None
    icon_id: str | None = None


class EquipmentReader:
    def __init__(self,observer):
        self.o=observer

    def item(self,model,kind):
        if not model:return None
        descriptor=self.o.ref(model,'canpbkiogjm')
        template=self.o.ref(descriptor,'eocjokmmcge') if descriptor else 0
        if not template:return None
        # onobdmohahp's native getters resolve the cached template at
        # eocjokmmcge (0x644E90), then nhjofmmmngl / lleaklpfafc.
        system_id=self.o.string(template,'nhjofmmmngl')
        brand=self.o.string(template,'lleaklpfafc')
        if not system_id or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',system_id):return None
        fields={f['name'] for f in self.o.metadata.all_fields(self.o.cls(descriptor))}
        template_fields={f['name'] for f in self.o.metadata.all_fields(self.o.cls(template))}
        condition=self.o.number(descriptor,'nmidlgejlcp') if 'nmidlgejlcp' in fields else None
        strength=self.o.number(descriptor,'nlmnpekipjc') if 'nlmnpekipjc' in fields else None
        nominal=self.o.number(template,'kngaaefkpka') if 'kngaaefkpka' in template_fields else None
        if condition is not None and not 0<=condition<=1.001:condition=None
        if strength is not None and not 0<strength<=100000:strength=None
        if nominal is not None and not 0<nominal<=100000:nominal=None
        quantity=self.o.integer(descriptor,'ljnnpokapig') if kind=='bait' and 'ljnnpokapig' in fields else None
        if quantity is not None and not 0<=quantity<=10000000:quantity=None
        length=diameter=mass=None
        icon_id=system_id
        if kind=='line':
            if 'ljnnpokapig' in fields:length=self.o.integer(descriptor,'ljnnpokapig')
            if 'ciichedlnjh' in template_fields:diameter=self.o.number(template,'ciichedlnjh')
        elif kind=='leader':
            # The inventory shows this template length in centimetres.
            if 'hkgndoipdlc' in template_fields:length=self.o.number(template,'hkgndoipdlc')/100
            # Crafted leaders retain their material template separately.
            for name in ('mbnambppbom','baadhdmaonp'):
                material=self.o.ref(descriptor,name) if name in fields else 0
                material_template=self.o.ref(material,'eocjokmmcge') if material else 0
                if not material_template:continue
                material_fields={f['name'] for f in self.o.metadata.all_fields(self.o.cls(material_template))}
                if 'ciichedlnjh' in material_fields:diameter=self.o.number(material_template,'ciichedlnjh')
                if 'kngaaefkpka' in material_fields:nominal=self.o.number(material_template,'kngaaefkpka')
                material_id=self.o.string(material_template,'nhjofmmmngl')
                if material_id and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',material_id):icon_id=material_id
                break
        elif kind=='rod' and 'hkgndoipdlc' in template_fields:
            length=self.o.number(template,'hkgndoipdlc')
        if kind in ('sinker','reel','rod') and 'dhlkahnodoo' in template_fields:
            mass=self.o.number(template,'dhlkahnodoo')*(1000 if kind=='reel' else 1)
        elif kind in ('hook','bait'):
            source=descriptor if 'ijbjficbhog' in fields else template if 'ijbjficbhog' in template_fields else 0
            if source:mass=self.o.number(source,'ijbjficbhog')
        if length is not None and not 0<length<=10000:length=None
        if diameter is not None and not 0<diameter<=100:diameter=None
        if mass is not None and not 0<mass<=100000:mass=None
        if nominal is not None and not 0<nominal<=100000:nominal=None
        return EquipmentItem(kind,system_id,brand,condition,strength,nominal,quantity,length,diameter,mass,icon_id)

    def read(self,tackle,rig):
        result=[]
        def add(model,kind):
            item=self.item(model,kind)
            if item and not any(x.kind==item.kind and x.system_id==item.system_id for x in result):result.append(item)
        try:
            rod=self.o.ref(tackle,'okncibgkfdd')
            if rod:add(self.o.ref(rod,'coffdfkgfaa'),'rod')
            fields={f['name'] for f in self.o.metadata.all_fields(self.o.cls(tackle))}
            reel=self.o.ref(tackle,'mdokjmcfnch') if 'mdokjmcfnch' in fields else 0
            if reel:add(self.o.ref(reel,'<nfjcgaalamm>k__BackingField'),'reel')
            rig_model=self.o.ref(rig,'coffdfkgfaa')
            model_fields={f['name'] for f in self.o.metadata.all_fields(self.o.cls(rig_model))} if rig_model else set()
            part=self.o.ref(rig_model,'ldajhmpkhho') if 'ldajhmpkhho' in model_fields else 0
            seen=set()
            # The complete slot list includes bait and alarms which are not
            # part of the hook -> line -> reel strength chain.
            kinds={'jbipdjaplgk':'hook','lapcaghijic':'leader','jighdckhmbn':'sinker',
                   'dgmaokfcpke':'line','lkgakdhinig':'reel','jbileadfpkp':'bait',
                   'fhdclojjgle':'alarm'}
            slots=object_list(self.o,self.o.ref(rig_model,'dodebooapfn'),32) if 'dodebooapfn' in model_fields else ()
            if not slots:
                chain=[]
                for _ in range(16):
                    if not part or part in seen:break
                    seen.add(part);chain.append(part)
                    part=self.o.ref(part,'<ekdllbjojde>k__BackingField')
                slots=chain
            for slot in slots:
                model=self.o.ref(slot,'nnghlepcnlf')
                if model:add(model,kinds.get(self.o.cls(model)['full_name'],'component'))
        except (OSError,ValueError,StopIteration,KeyError):
            # An unavailable icon/name must not disconnect load protection.
            pass
        return tuple(result)
