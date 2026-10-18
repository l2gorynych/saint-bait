from dataclasses import replace
import unittest
from saint_bait.automatic_drag import BrakeCalibration,SAFETY_FRACTION
from saint_bait.rods import RodView,RodPhase


class AutomaticDragTests(unittest.TestCase):
    def rod(self,step,force=None):
        return RodView('a','feeder',active=True,memory_metrics=True,phase=RodPhase.READY,
            load_force=0.,tackle_limit=100.,drag_setting=step,drag_force=force if force is not None else step*5.,drag_locked=False)

    def calibrate(self,initial):
        control=BrakeCalibration('a')
        step=initial
        for _ in range(60):
            direction=control.observe(self.rod(step))
            if not direction:return step,control.profile()
            step+=direction
        self.fail('Calibration did not converge')

    def test_same_maximum_is_found_from_above_and_below(self):
        for initial in (1,5,20,29):
            step,profile=self.calibrate(initial)
            self.assertEqual(step,16)
            self.assertEqual(profile.maximum(100.),16)
            self.assertLessEqual(profile.force_at(step),100.*SAFETY_FRACTION)
            self.assertGreater(profile.force_at(step+1),100.*SAFETY_FRACTION)

    def test_blocked_30_is_lowered_and_never_used_as_a_real_force(self):
        self.assertEqual(BrakeCalibration('a').observe(replace(self.rod(30),drag_locked=True,drag_force=None)),-1)
        self.assertEqual(BrakeCalibration('a').observe(self.rod(29,50.)),0)

    def test_loaded_or_hooked_rods_are_never_used_for_calibration(self):
        for changes in ({'hooked':True},{'phase':RodPhase.DEPLOYED},{'load_force':20.},{'active':False}):
            with self.assertRaises(ValueError):BrakeCalibration('a').observe(replace(self.rod(10),**changes))

    def test_unsafe_even_on_minimum_cancels_fishing(self):
        with self.assertRaises(ValueError):BrakeCalibration('a').observe(self.rod(1,90.))

    def test_profile_ceiling_falls_if_tackle_strength_falls(self):
        _,profile=self.calibrate(1)
        self.assertLess(profile.maximum(70.),profile.maximum(100.))
