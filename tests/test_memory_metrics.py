import struct
import unittest
from types import SimpleNamespace
from saint_bait.telemetry.observer import TackleObserver


class MetricGetterTests(unittest.TestCase):
    def observer(self):
        value=object.__new__(TackleObserver)
        value.r=SimpleNamespace(read=lambda address,size:struct.pack('<i',2))
        value.field=lambda obj,name:dict(type='kieibhlheed',type_code=17,offset=304)
        value.ref=lambda obj,name:{'imdaclihign':10,'fcpagkkekeb':20}[name]
        value.cls=lambda obj:dict(full_name={10:'RF4.Client.FishingScene.RigConnector',20:'ihlkhcenhfc'}[obj])
        value.number=lambda obj,name:{'pkpijfjceof':7.8,'koomajjcigp':66.,'jbheonnnbhe':132.}[name]
        value.brake=lambda obj:(80.,20,False)
        return value

    def test_metric_ratio_matches_stock_hud_formula(self):
        metrics=self.observer().metrics(1)
        self.assertEqual((metrics.code,metrics.line,metrics.fraction),(2,7.8,.5))
        self.assertEqual((metrics.current,metrics.limit,metrics.drag),(66.,132.,80.))

    def test_invalid_line_length_is_rejected(self):
        value=self.observer()
        value.number=lambda obj,name:-1
        with self.assertRaises(ValueError): value.metrics(1)

    def test_unknown_phase_is_rejected(self):
        value=self.observer()
        value.r=SimpleNamespace(read=lambda address,size:struct.pack('<i',42))
        with self.assertRaises(ValueError): value.metrics(1)

    def brake_observer(self,step=18,force=70.,heat=.5):
        value=object.__new__(TackleObserver)
        value.metadata=SimpleNamespace(all_fields=lambda cls:[{'name':'mdokjmcfnch'}])
        value.cls=lambda obj:dict(full_name={1:'RF4.Client.FishingScene.RodReelRigFishingSet',
                                           2:'RF4.Client.FishingScene.Reel',3:'lkgakdhinig'}[obj])
        value.ref=lambda obj,name:2 if obj==1 else 3
        value.integer=lambda obj,name:step
        value.number=lambda obj,name:heat if obj==2 else force
        return value

    def test_effective_brake_matches_game_heat_correction(self):
        drag,setting,locked=self.brake_observer().brake(1)
        self.assertAlmostEqual(drag,68.25)
        self.assertEqual((setting,locked),(19,False))

    def test_locked_brake_is_not_treated_as_unlimited_tackle_strength(self):
        self.assertEqual(self.brake_observer(29,3.402823466e38).brake(1),(None,30,True))
        with self.assertRaises(ValueError): self.brake_observer(29,70.).brake(1)

    def test_setting_changed_during_read_is_rejected(self):
        value=self.brake_observer()
        values=iter((18,19))
        value.integer=lambda obj,name:next(values)
        with self.assertRaises(ValueError): value.brake(1)


if __name__=='__main__': unittest.main()
