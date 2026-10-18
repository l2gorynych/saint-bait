import unittest
from saint_bait.rods import RodRegistry, RodView, RodPhase, classify_screen, classify_memory


class RodStateTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.
        self.registry = RodRegistry(lambda:self.now)

    def test_failed_ocr_never_means_ready(self):
        for value in (None,999,-1,float('nan'),True):
            self.assertEqual(classify_screen(fish=False,catch=False,distance=value),RodPhase.UNKNOWN)
        self.assertEqual(classify_screen(fish=False,catch=False,distance=0),RodPhase.READY)
        self.assertEqual(classify_screen(fish=False,catch=False,distance=25),RodPhase.REEL_IN)

    def test_fish_and_catch_do_not_depend_on_distance_ocr(self):
        self.assertEqual(classify_screen(fish=True,catch=False,distance=999),RodPhase.HOOKED)
        self.assertEqual(classify_screen(fish=True,catch=True,distance=999),RodPhase.CATCH)

    def test_binding_follows_identity_when_active_rod_leaves_rest_list(self):
        self.registry.update(1,[RodView('a','feeder',active=True),RodView('b','feeder',on_rest=True)])
        self.assertEqual(self.registry.bind_active('1'),'a')
        self.registry.observe_screen('1',fish=False,catch=False,distance=20)
        self.registry.update(1,[RodView('b','feeder',on_rest=True),RodView('a','feeder',on_rest=True)])
        item=next(x for x in self.registry.snapshot() if x.identity=='a')
        self.assertEqual(item.slot_key,'1')
        self.assertEqual(item.phase,RodPhase.DEPLOYED)
        self.assertIs(item.cast,True)

    def test_stale_or_unavailable_observations_cannot_select_fish(self):
        self.registry.update(1,[RodView('a','feeder',active=True,hooked=True)])
        self.registry.bind_active('2')
        self.assertEqual(self.registry.fish_priority().slot_key,'2')
        self.now=13.
        self.assertIsNone(self.registry.fish_priority())
        self.now=10.
        self.registry.unavailable('disconnected')
        self.assertIsNone(self.registry.fish_priority())

    def test_new_process_forgets_slot_bindings_and_cast_flags(self):
        self.registry.update(1,[RodView('a','feeder',active=True)])
        self.registry.bind_active('1')
        self.registry.observe_screen('1',fish=False,catch=False,distance=0)
        self.registry.update(2,[RodView('a','feeder',active=True)])
        item=self.registry.snapshot()[0]
        self.assertIsNone(item.slot_key)
        self.assertIsNone(item.cast)

    def test_pickup_animation_preserves_binding_but_never_serves_missing_rod(self):
        self.registry.update(1,[RodView('a','feeder',active=True,hooked=True)])
        self.registry.bind_active('3')
        self.registry.update(1,[])
        self.assertEqual(self.registry.snapshot(),())
        self.assertIsNone(self.registry.fish_priority())
        self.now+=1
        self.registry.update(1,[RodView('a','feeder',active=True,hooked=True)])
        self.assertEqual(self.registry.fish_priority().slot_key,'3')

    def test_binding_conflicts_fail_instead_of_guessing(self):
        self.registry.update(1,[RodView('a','feeder',active=True)])
        self.registry.bind_active('1')
        with self.assertRaises(ValueError): self.registry.bind_active('2')

    def test_two_active_rods_are_not_assigned(self):
        self.registry.update(1,[RodView('a','feeder',active=True),RodView('b','feeder',active=True)])
        self.assertIsNone(self.registry.bind_active('1'))

    def test_input_sequence_alone_does_not_confirm_deployment(self):
        self.registry.update(1,[RodView('a','feeder',active=True)])
        self.registry.bind_active('1')
        self.registry.mark_casting('1')
        self.registry.mark_cast_complete('1')
        self.assertIsNone(self.registry.snapshot()[0].cast)

    def test_native_state_sets_cast_flags_without_screen_ocr(self):
        for code,active,rest,expected,cast in (
            (0,True,False,RodPhase.READY,False),
            (2,False,True,RodPhase.DEPLOYED,True),
            (2,True,False,RodPhase.REEL_IN,True),
            (98,True,False,RodPhase.UNKNOWN,None)):
            self.assertEqual(classify_memory(code=code,pending=False,hooked=False,active=active,on_rest=rest),(expected,cast))

    def test_fresh_native_phase_overrides_old_cast_ledger(self):
        self.registry.update(1,[RodView('a','feeder',active=True)])
        self.registry.bind_active('1')
        self.registry.observe_screen('1',fish=False,catch=False,distance=0)
        self.registry.update(1,[RodView('a','feeder',on_rest=True,memory_metrics=True,
                                       state_code=2,phase=RodPhase.DEPLOYED,cast=True,line_m=7.8)])
        self.assertEqual(self.registry.snapshot()[0].phase,RodPhase.DEPLOYED)
        self.assertIs(self.registry.snapshot()[0].cast,True)


if __name__=='__main__': unittest.main()
