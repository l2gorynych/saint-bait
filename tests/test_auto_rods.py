from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from saint_bait import state
from saint_bait.auto_rods import AutoRodController
from saint_bait.controls import SessionCancelled
from saint_bait.rods import RodRegistry, RodView, RodPhase


class AutomaticRodTests(unittest.TestCase):
    def setUp(self):
        state.stop_event.clear()
        self.registry=RodRegistry()
        self.registry.update(1,[RodView('a','feeder',active=True)])
        self.registry.bind_active('1')
        self.ui=SimpleNamespace(rod_registry=self.registry,entry_reel_btn=SimpleNamespace(get=lambda:'left'))
        self.controller=AutoRodController(self.ui)

    def tearDown(self):
        state.stop_event.clear()

    def test_ready_cast_never_reels(self):
        self.controller.select=Mock()
        self.controller.observe=Mock(return_value=RodPhase.READY)
        with patch('saint_bait.auto_rods.safe_mouse') as mouse:
            self.assertTrue(self.controller.before_cast(None,None,'1'))
        self.assertFalse(any(call.args[0]=='down' for call in mouse.call_args_list))

    def test_line_is_retrieved_before_cast_becomes_ready(self):
        self.controller.select=Mock()
        self.controller.observe=Mock(side_effect=[RodPhase.REEL_IN,RodPhase.READY,RodPhase.READY])
        with (patch('saint_bait.auto_rods.safe_mouse') as mouse,
              patch('saint_bait.auto_rods.human_sleep'),patch('saint_bait.auto_rods.log')):
            self.assertTrue(self.controller.before_cast(None,None,'1'))
        self.assertEqual([call.args[0] for call in mouse.call_args_list],['down','up','up'])

    def test_unknown_and_hooked_rigs_block_cast_without_mouse_down(self):
        self.controller.select=Mock()
        for phase in (RodPhase.UNKNOWN,RodPhase.HOOKED,RodPhase.CATCH):
            with self.subTest(phase=phase):
                state.stop_event.clear()
                self.controller.observe=Mock(return_value=phase)
                with patch('saint_bait.auto_rods.safe_mouse') as mouse,patch('saint_bait.auto_rods.log'):
                    with self.assertRaises(SessionCancelled): self.controller.before_cast(None,None,'1')
                mouse.assert_not_called()

    def test_fish_priority_selects_its_verified_slot(self):
        self.registry.update(1,[RodView('a','feeder',active=True,hooked=True)])
        self.controller.select=Mock()
        self.controller.wait_active=Mock(return_value=self.registry.snapshot()[0])
        with patch('saint_bait.auto_rods.log'):
            self.assertTrue(self.controller.priority(['3','1','2']))
        self.controller.select.assert_called_once_with('1',urgent=True)
        self.assertEqual(state.cur_idx,1)
        self.assertEqual(state.state,1)

    def test_cast_completion_waits_for_line_in_water(self):
        self.controller.observe=Mock(side_effect=[RodPhase.READY,RodPhase.UNKNOWN,RodPhase.REEL_IN])
        with patch('saint_bait.auto_rods.human_sleep') as delay:
            self.controller.after_cast(None,None,'1')
        self.assertEqual(delay.call_count,2)

    def test_unconfirmed_cast_stops_instead_of_being_marked_deployed(self):
        self.controller.observe=Mock(return_value=RodPhase.READY)
        with patch('saint_bait.auto_rods.time.monotonic',side_effect=[0,1,6]),patch('saint_bait.auto_rods.human_sleep'):
            with self.assertRaises(SessionCancelled): self.controller.after_cast(None,None,'1')
        self.assertTrue(state.stop_event.is_set())

    def test_calibration_preserves_already_cast_rods(self):
        initial=[RodView('a','feeder',on_rest=True),RodView('b','feeder',on_rest=True),RodView('c','feeder',on_rest=True)]
        self.registry=RodRegistry()
        self.registry.update(1,initial)
        self.ui.rod_registry=self.registry
        controller=AutoRodController(self.ui)
        def choose(key,ui):
            chosen={'1':'c','2':'a','3':'b'}[key]
            self.registry.update(1,[replace(x,active=x.identity==chosen,on_rest=x.identity!=chosen) for x in initial])
        def rest(ui):
            self.registry.update(1,[replace(x,active=False,on_rest=True) for x in initial])
        controller.observe=lambda sct,win,key:self.registry.observe_screen(key,fish=False,catch=False,distance=30)
        with (patch('saint_bait.auto_rods.human_press',side_effect=choose),
              patch('saint_bait.auto_rods.put_rod_on_stand',side_effect=rest),
              patch('saint_bait.auto_rods.human_sleep'),patch('saint_bait.auto_rods.log')):
            self.assertEqual(controller.prepare(None,None,['1','2','3']),[])
        mapping={x.slot_key:x.identity for x in self.registry.snapshot()}
        self.assertEqual(mapping,{'1':'c','2':'a','3':'b'})
        self.assertTrue(all(x.cast is True and x.phase==RodPhase.DEPLOYED for x in self.registry.snapshot()))

    def test_memory_observation_and_distance_do_not_call_ocr(self):
        self.registry.update(1,[RodView('a','feeder',active=True,memory_metrics=True,
                                       phase=RodPhase.REEL_IN,line_m=7.8,load_fraction=.3)])
        self.assertEqual(self.controller.observe(None,None,'1'),RodPhase.REEL_IN)
        self.assertEqual(self.controller.distance(),7.8)

    def test_empty_hands_start_casts_each_ready_rod_as_soon_as_picked_up(self):
        initial=[RodView('a','feeder',on_rest=True,memory_metrics=True,phase=RodPhase.READY),
                 RodView('b','feeder',on_rest=True,memory_metrics=True,phase=RodPhase.DEPLOYED),
                 RodView('c','feeder',on_rest=True,memory_metrics=True,phase=RodPhase.READY)]
        registry=RodRegistry()
        registry.update(1,initial)
        self.ui.rod_registry=registry
        controller=AutoRodController(self.ui)
        trace=[]
        def choose(key,ui):
            trace.append('take '+key)
            identity={'1':'a','2':'b','3':'c'}[key]
            registry.update(1,[replace(x,active=x.identity==identity,on_rest=x.identity!=identity)
                               for x in registry.snapshot()])
        def rest(ui):
            trace.append('rest')
            registry.update(1,[replace(x,active=False,on_rest=True) for x in registry.snapshot()])
        def cast(rod):
            trace.append('cast '+rod.slot_key)
            registry.update(1,[replace(x,phase=RodPhase.DEPLOYED if x.identity==rod.identity else x.phase)
                               for x in registry.snapshot()])
            rest(self.ui)
        with (patch('saint_bait.auto_rods.human_press',side_effect=choose),
              patch('saint_bait.auto_rods.put_rod_on_stand',side_effect=rest),
              patch('saint_bait.auto_rods.human_sleep'),patch('saint_bait.auto_rods.log')):
            self.assertEqual(controller.prepare(None,None,['1','2','3'],on_ready=cast),[])
        self.assertEqual(trace,['take 1','cast 1','rest','take 2','rest','take 3','cast 3','rest'])
        self.assertTrue(all(x.phase==RodPhase.DEPLOYED and x.on_rest and not x.active for x in registry.snapshot()))

    def test_all_deployed_rods_are_not_picked_up_even_without_slot_mapping(self):
        self.registry.update(1,[RodView('a','feeder',on_rest=True,memory_metrics=True,phase=RodPhase.DEPLOYED),
                                RodView('b','feeder',on_rest=True,memory_metrics=True,phase=RodPhase.DEPLOYED)])
        cast=Mock()
        with patch('saint_bait.auto_rods.human_press') as press,patch('saint_bait.auto_rods.log'):
            self.assertEqual(self.controller.prepare(None,None,['1','2'],on_ready=cast),[])
        press.assert_not_called()
        cast.assert_not_called()

    def test_memory_load_has_hysteresis(self):
        decisions=[]
        for load in (76.,78.,72.,70.):
            self.registry.update(1,[RodView('a','feeder',active=True,memory_metrics=True,
                                           phase=RodPhase.HOOKED,hooked=True,load_force=load,
                                           tackle_limit=132.,drag_force=80.,drag_locked=False)])
            decisions.append(self.controller.overload())
        self.assertEqual(decisions,[False,True,True,False])

    def test_threshold_follows_brake_change_without_restart(self):
        decisions=[]
        for drag in (100.,60.,100.):
            self.registry.update(1,[RodView('a','feeder',active=True,memory_metrics=True,
                phase=RodPhase.HOOKED,load_force=70.,tackle_limit=132.,drag_force=drag,drag_locked=False)])
            decisions.append(self.controller.overload())
        self.assertEqual(decisions,[False,True,False])

    def test_missing_load_stops_retrieval(self):
        self.registry.update(1,[RodView('a','feeder',active=True,memory_metrics=True,
                                       phase=RodPhase.HOOKED,hooked=True,load_fraction=None)])
        with self.assertRaises(SessionCancelled): self.controller.overload()
        self.assertTrue(state.stop_event.is_set())

    def test_attached_fish_is_taken_from_memory(self):
        self.registry.update(1,[RodView('a','feeder',active=True,memory_metrics=True,hooked=True,
                                       phase=RodPhase.HOOKED,line_m=7.8,load_fraction=.3)])
        self.assertTrue(self.controller.fish_attached())
        self.registry.update(1,[RodView('a','feeder',active=True,memory_metrics=True,hooked=False,
                                       phase=RodPhase.REEL_IN,line_m=7.8,load_fraction=.3)])
        self.assertFalse(self.controller.fish_attached())


if __name__=='__main__': unittest.main()
