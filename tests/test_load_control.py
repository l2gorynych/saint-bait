from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import random
import unittest
from saint_bait import state
from saint_bait.rods import RodView,RodPhase
from saint_bait.load_control import LoadInputGuard,load_limits
from saint_bait.pacing import ActionPacing
from saint_bait.controls import SessionCancelled


class LoadControlTests(unittest.TestCase):
    def setUp(self):
        state.stop_event.clear()
        state.is_casting=False
        self.rod=RodView('a','feeder',active=True,phase=RodPhase.HOOKED,
            load_force=40.,tackle_limit=100.,drag_force=60.,drag_locked=False)
        self.blocked=False
        self.controller=SimpleNamespace(active=lambda **kwargs:self.rod,overload=lambda:self.blocked)
        self.down,self.up=Mock(),Mock()
        self.guard=LoadInputGuard(self.controller,('left','right'),self.down,self.up)

    def tearDown(self):
        self.guard.stop()
        state.stop_event.clear()

    def test_drag_and_tackle_strength_both_limit_input(self):
        release,resume=load_limits(self.rod)
        self.assertAlmostEqual(release,58.2)
        self.assertAlmostEqual(resume,52.8)
        limits=load_limits(replace(self.rod,drag_force=150.))
        self.assertEqual(limits,(97.,88.))
        self.assertEqual(load_limits(replace(self.rod,drag_force=None,drag_locked=True)),limits)

    def test_missing_or_nonfinite_metrics_do_not_allow_input(self):
        for changes in ({'drag_locked':None},{'load_force':float('nan')},
                        {'tackle_limit':0.},{'drag_force':float('inf')}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                load_limits(replace(self.rod,**changes))

    def test_guard_releases_during_engine_pause_and_resumes_requested_hold(self):
        self.guard.request('down','left')
        self.down.assert_called_once_with(button='left',_pause=False)
        self.blocked=True
        self.guard.refresh()
        self.up.assert_called_once_with(button='left',_pause=False)
        self.blocked=False
        self.guard.refresh()
        self.assertEqual(self.down.call_count,2)

    def test_up_during_overload_cancels_any_future_resume(self):
        self.blocked=True
        self.guard.request('down','left')
        self.guard.request('up','left')
        self.blocked=False
        self.guard.refresh()
        self.down.assert_not_called()

    def test_stop_clears_requested_hold_and_never_resumes(self):
        self.guard.request('down','left')
        state.stop_event.set()
        self.guard.refresh()
        state.stop_event.clear()
        self.guard.refresh()
        self.assertEqual(self.down.call_count,1)
        with self.assertRaises(SessionCancelled):
            self.guard.stop()
            self.guard.request('down','left')

    def test_absent_or_changed_rod_cancels_input(self):
        self.guard.request('down','left')
        self.rod=replace(self.rod,identity='b')
        with self.assertRaises(SessionCancelled): self.guard.request('down','right')
        self.rod=None
        with self.assertRaises(SessionCancelled): self.guard.request('down','left')
        self.assertFalse(self.guard._held)

    def test_ready_and_catch_transitions_release_without_accidental_cast(self):
        for phase in (RodPhase.READY,RodPhase.CATCH):
            with self.subTest(phase=phase):
                self.rod=replace(self.rod,phase=RodPhase.HOOKED)
                self.guard.request('down','left')
                downs=self.down.call_count
                self.rod=replace(self.rod,phase=phase)
                self.guard.refresh()
                self.guard.refresh()
                self.assertFalse(self.guard._held)
                self.assertEqual(self.down.call_count,downs)

    def test_explicit_cast_can_start_from_ready_phase(self):
        state.is_casting=True
        self.rod=replace(self.rod,phase=RodPhase.READY)
        self.guard.request('down','left')
        self.down.assert_called_once_with(button='left',_pause=False)
        self.guard.request('up','left')
        state.is_casting=False

    def test_pacing_is_bounded_and_urgent_actions_have_no_extra_delay(self):
        pacing=ActionPacing(random.Random(42))
        for action,(low,high,_) in pacing.RANGES.items():
            samples=[pacing.delay(action) for _ in range(100)]
            self.assertTrue(all(low<=delay<=high for delay in samples))
            self.assertGreater(len(set(samples)),90)
            self.assertEqual(pacing.delay(action,urgent=True),0.)


if __name__=='__main__': unittest.main()
