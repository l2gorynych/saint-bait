from types import SimpleNamespace
import unittest
from saint_bait.telemetry.equipment import EquipmentReader,EquipmentItem
from saint_bait.equipment_text import measurements


class NativeItems:
    def __init__(self,kind,template,descriptor=None,material=None):
        self.data={'model':{'canpbkiogjm':'descriptor'},
                   'descriptor':{'eocjokmmcge':'template','nmidlgejlcp':.977,
                                 'nlmnpekipjc':13.13,**(descriptor or {})},
                   'template':{'nhjofmmmngl':'native_item','lleaklpfafc':'brand',**template}}
        if material:
            self.data['descriptor']['mbnambppbom']='material'
            self.data['material']={'eocjokmmcge':'material_template'}
            self.data['material_template']=material
        self.metadata=SimpleNamespace(all_fields=lambda key:[{'name':name} for name in self.data[key]])
    def cls(self,key):return key
    def ref(self,key,name):return self.data[key][name]
    def number(self,key,name):return self.data[key][name]
    def integer(self,key,name):return self.data[key][name]
    def string(self,key,name):return self.data[key].get(name)


class EquipmentTests(unittest.TestCase):
    def test_crafted_leader_length_is_centimetres_and_material_supplies_icon_and_nominal(self):
        native=NativeItems('leader',{'hkgndoipdlc':60},material={
            'ciichedlnjh':.24,'lgjeahdobch':.13,'kngaaefkpka':13.6,'nhjofmmmngl':'br_leader_40087'})
        item=EquipmentReader(native).item('model','leader')
        self.assertEqual(item.length_m,.6)
        self.assertEqual(item.diameter_mm,.24)
        self.assertEqual(item.strength_kg,13.13)
        self.assertEqual(item.nominal_kg,13.6)
        self.assertEqual(item.icon_id,'br_leader_40087')
        self.assertEqual(measurements(item),'60 см · Ø 0,24 мм')

    def test_line_length_is_not_bait_quantity_and_rod_length_uses_metres(self):
        native=NativeItems('line',{'ciichedlnjh':.24,'lgjeahdobch':.01},descriptor={'ljnnpokapig':300})
        item=EquipmentReader(native).item('model','line')
        self.assertEqual(item.length_m,300)
        self.assertIsNone(item.quantity)
        self.assertEqual(measurements(item),'300 м · Ø 0,24 мм')
        rod=EquipmentReader(NativeItems('rod',{'hkgndoipdlc':3,'dhlkahnodoo':246})).item('model','rod')
        self.assertEqual(measurements(rod),'3 м · 246 г')

    def test_mass_uses_native_units_for_reel_sinker_and_bait(self):
        for kind,template,expected in [('reel',{'dhlkahnodoo':.317},317),
                                     ('sinker',{'dhlkahnodoo':30},30),('bait',{'ijbjficbhog':5},5)]:
            with self.subTest(kind=kind):
                self.assertAlmostEqual(EquipmentReader(NativeItems(kind,template)).item('model',kind).mass_g,expected)

    def test_invalid_specs_are_unknown_and_history_uses_the_same_units(self):
        item=EquipmentReader(NativeItems('line',{'ciichedlnjh':-1},descriptor={'ljnnpokapig':-3})).item('model','line')
        self.assertIsNone(item.length_m);self.assertIsNone(item.diameter_mm)
        self.assertEqual(measurements({'kind':'leader','length_m':.6,'diameter_mm':.13}),'60 см · Ø 0,13 мм')
        self.assertEqual(measurements(EquipmentItem('hook','id')),'')
