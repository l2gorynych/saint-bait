from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from saint_bait import state
from saint_bait.rods import RodRegistry,RodView,RodPhase
from saint_bait.bindings import resolve_bindings
from saint_bait.game_input import input_token
from saint_bait.telemetry.scene import SceneView
from saint_bait.runtime import MemorySession,resolve_mode
from saint_bait.controls import SessionCancelled
from saint_bait.strategies.feeder import FeederStrategy
from saint_bait.strategies.spinning import SpinningStrategy
from saint_bait.hud import compact_line


def entry(value):return SimpleNamespace(get=lambda:str(value))


class MemoryRuntimeTests(unittest.TestCase):
    def setUp(self):
        state.stop_event.clear()
        receipt_patch=patch('saint_bait.runtime.open',create=True)
        receipt_patch.start()
        self.addCleanup(receipt_patch.stop)
        self.registry=RodRegistry()
        self.rod=RodView('a','feeder',active=True,memory_metrics=True,phase=RodPhase.CATCH,
                         load_force=0.,tackle_limit=132.,drag_force=120.,drag_locked=False)
        self.registry.update(1,[self.rod])
        self.registry.bind_active('1')
        self.bindings=tuple(sorted(dict(reel='mouse:left',pull='mouse:right',net=';',stand='left alt',slot1='1').items()))
        self.registry.update_scene(SceneView(bindings=self.bindings,dialogs=('RF4.Client.UI.GameResult.RUIGameResultDialog',),
            catch_id='dialog',catch_ready=True,keep_key='space',release_key='backspace'))
        self.ui=SimpleNamespace(rod_registry=self.registry,fishing_mode='feeder',
            check_do_gb=entry(False),entry_gb_key=entry(5),check_do_cons=entry(False),entry_cons_key=entry(4),
            check_catch_alerts=entry(False),check_release_fish=entry(False),
            entry_feeder_cast=entry(.8),entry_spinning_cast=entry(1.),entry_stop_time=entry(0),
            entry_clip=entry(8),
            entry_feeder_slots=entry('1,2,3'),entry_rod1=entry('1'),entry_rod2=entry('2'),entry_rod3=entry('3'),
            entry_reel_btn=entry('left'),entry_pull_btn=entry('right'),update_stats=Mock())
        # Flags return booleans, just like CachedCheckBox.
        for name in ('check_do_gb','check_do_cons','check_catch_alerts','check_release_fish'):
            setattr(self.ui,name,SimpleNamespace(get=lambda:False))
        self.session=MemorySession(self.ui)
        self.session.input=Mock(bindings=dict(self.bindings))

    def tearDown(self):state.stop_event.clear()

    def test_catch_confirm_uses_result_button_space_then_waits_for_closed_dialog(self):
        def accepted(key):
            self.assertEqual(key,'space')
            self.registry.update(1,[replace(self.rod,phase=RodPhase.READY)])
            self.registry.update_scene(SceneView(bindings=self.bindings))
        self.session.input.press_token.side_effect=accepted
        rod=self.registry.snapshot()[0]
        with patch('saint_bait.runtime.human_sleep'),patch('saint_bait.runtime.log'),patch('saint_bait.vision.catch_awards',return_value=(False,False)):
            self.session.confirm(rod)
        self.session.input.press_token.assert_called_once_with('space')
        self.ui.update_stats.assert_called_once_with(fish_inc=1,is_trophy=False,is_card=False,rod_idx=0)
        self.assertEqual(self.session.active().phase,RodPhase.READY)

    def test_unconfirmed_window_never_sends_accept_or_counts_fish(self):
        self.session.wait=Mock(side_effect=SessionCancelled('not ready'))
        with self.assertRaises(SessionCancelled):self.session.confirm(self.registry.snapshot()[0])
        self.session.input.press_token.assert_not_called()
        self.ui.update_stats.assert_not_called()

    def test_full_keepnet_blocks_start_and_cast_before_rod_input(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,keepnet_count=100,keepnet_capacity=100))
        self.session.controller=Mock()
        with self.assertRaisesRegex(SessionCancelled,'Садок заполнен'):self.session.prepare()
        self.session.controller.start.assert_not_called()
        self.session.apply_rod_settings=Mock()
        with self.assertRaisesRegex(SessionCancelled,'Садок заполнен'):self.session.cast(self.rod)
        self.session.apply_rod_settings.assert_not_called()
        self.session.input.hold.assert_not_called()

    def test_missing_keepnet_count_does_not_authorize_casting(self):
        self.registry.update_scene(SceneView(bindings=self.bindings))
        self.session.apply_rod_settings=Mock()
        with self.assertRaisesRegex(SessionCancelled,'проверить место в садке'):self.session.cast(self.rod)
        self.session.apply_rod_settings.assert_not_called()

    def test_full_keepnet_leaves_qualified_catch_for_manual_decision(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,catch_id='result',catch_ready=True,
            keep_key='space',release_key='backspace',keepnet_count=100,keepnet_capacity=100))
        with (patch('saint_bait.runtime.human_sleep'),patch('saint_bait.vision.catch_awards',return_value=(False,False))):
            with self.assertRaisesRegex(SessionCancelled,'Рыба оставлена'):
                self.session.confirm(replace(self.registry.snapshot()[0],grade=2))
        self.session.input.press_token.assert_not_called()
        self.ui.update_stats.assert_not_called()

    def test_full_native_capacity_stops_before_any_next_cast(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,keepnet_count=150,keepnet_capacity=150))
        self.session.prepare=Mock()
        self.session.cast_ready=Mock()
        self.session.select=Mock()
        with patch('saint_bait.auxiliary.AuxiliaryActions'),patch('saint_bait.runtime.log') as logged:
            self.session.run()
        self.session.select.assert_not_called()
        self.session.cast_ready.assert_not_called()
        self.assertIn('150/150',logged.call_args.args[0])

    def test_old_two_fish_task_limit_does_not_stop_normal_fishing(self):
        import configparser
        config=configparser.ConfigParser()
        config.read_dict({'Settings':{'catch_limit':'2'}})
        self.ui.config=config
        self.registry.update(1,[replace(self.rod,phase=RodPhase.READY)])
        self.registry.update_scene(SceneView(bindings=self.bindings,keepnet_count=30,keepnet_capacity=100))
        session=MemorySession(self.ui)
        session.caught=2
        session.input=Mock(bindings=dict(self.bindings))
        session.prepare=Mock()
        session.cast_ready=Mock(side_effect=lambda rod:state.stop_event.set())
        session.select=lambda rod:rod
        with patch('saint_bait.auxiliary.AuxiliaryActions'),patch('saint_bait.runtime.human_sleep'):session.run()
        session.cast_ready.assert_called_once()

    def test_two_hour_limit_stops_without_a_new_action(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,keepnet_count=30,keepnet_capacity=100))
        self.session.prepare=Mock()
        self.session.select=Mock()
        with (patch('saint_bait.auxiliary.AuxiliaryActions'),patch('saint_bait.runtime.log'),
              patch('saint_bait.runtime.time.monotonic',return_value=self.session.started+7200)):
            self.session.run()
        self.session.select.assert_not_called()
        self.session.input.release.assert_called()

    def test_session_time_is_capped_at_two_hours_even_for_old_unlimited_settings(self):
        self.assertEqual(self.session.limit_s,7200)
        self.ui.entry_stop_time=entry(300)
        self.assertEqual(MemorySession(self.ui).limit_s,7200)
        self.ui.entry_stop_time=entry(60)
        self.assertEqual(MemorySession(self.ui).limit_s,3600)

    def test_key_press_without_dialog_closure_does_not_count_fish(self):
        scene=self.registry.scene()
        self.session.wait=Mock(side_effect=[scene,SessionCancelled('still open')])
        with patch('saint_bait.runtime.human_sleep'),patch('saint_bait.vision.catch_awards',return_value=(False,False)):
            with self.assertRaises(SessionCancelled):self.session.confirm(self.registry.snapshot()[0])
        self.session.input.press_token.assert_called_once_with('space')
        self.ui.update_stats.assert_not_called()

    def test_cycle_confirms_once_then_recasts_only_after_native_ready(self):
        trace=[]
        self.registry.update(1,[replace(self.rod,phase=RodPhase.READY)])
        self.registry.update_scene(SceneView(bindings=self.bindings))
        self.session.prepare=Mock()
        def cast(rod):
            trace.append('cast')
            if trace.count('cast')==2:
                state.stop_event.set()
            else:
                self.registry.update(1,[replace(self.rod,phase=RodPhase.HOOKED,hooked=True)])
        def retrieve(rod):
            trace.append('retrieve')
            self.registry.update(1,[replace(self.rod,phase=RodPhase.CATCH)])
            self.registry.update_scene(SceneView(bindings=self.bindings,dialogs=('RF4.Client.UI.GameResult.RUIGameResultDialog',),
                catch_id='result',catch_ready=True,keep_key='space'))
        def accept(key):
            trace.append('confirm')
            self.registry.update_scene(SceneView(bindings=self.bindings))
            self.registry.update(1,[replace(self.rod,phase=RodPhase.READY)])
        self.session.cast=cast
        self.session.retrieve=retrieve
        self.session.input.press_token.side_effect=accept
        with (patch('saint_bait.runtime.human_sleep'),patch('saint_bait.runtime.log'),
              patch('saint_bait.auxiliary.AuxiliaryActions'),patch('saint_bait.vision.catch_awards',return_value=(False,False))):
            self.session.run()
        self.assertEqual(trace,['cast','retrieve','confirm','cast'])
        self.ui.update_stats.assert_called_once()

    def test_binding_changes_stop_session_instead_of_using_old_keys(self):
        self.registry.update_scene(SceneView(bindings=tuple((key,'g' if key=='net' else value) for key,value in self.bindings)))
        with self.assertRaises(SessionCancelled):self.session.scene()

    def test_foreign_dialog_blocks_fishing(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,dialogs=('RF4.Client.UI.Inventory',)))
        with self.assertRaises(SessionCancelled):self.session.scene()

    def test_result_model_keeps_catch_phase_after_native_rod_is_ready(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,catch_id='result',catch_ready=True,
            catch_species='c.roach',catch_weight_g=847,catch_grade=2))
        self.registry.update(1,[replace(self.rod,phase=RodPhase.READY,species=None,weight_g=None)])
        current=self.registry.snapshot()[0]
        self.assertEqual((current.phase,current.species,current.weight_g,current.grade),
                         (RodPhase.CATCH,'c.roach',847,2))

    def test_dialog_transition_releases_input_and_waits_for_result(self):
        unknown=SceneView(bindings=self.bindings,dialogs=('transition',))
        result=SceneView(bindings=self.bindings,dialogs=('result',),catch_id='result')
        with patch.object(self.registry,'scene',side_effect=[unknown,result]),patch('saint_bait.runtime.human_sleep'):
            self.assertEqual(self.session.scene().catch_id,'result')
        self.session.input.release.assert_called_once()

    def test_feeder_slot_numbers_resolve_to_custom_game_keys(self):
        self.registry.update_scene(SceneView(bindings=tuple(sorted({**dict(self.bindings),'slot4':'g'}.items()))))
        self.ui.entry_feeder_slots=entry('4')
        self.assertEqual(MemorySession(self.ui).keys,['g'])

    def test_cast_anchor_uses_view_captured_before_game_activation(self):
        anchor=SceneView(camera_id='camera',camera_angles=(80.,-12.))
        self.ui.cast_start_scene=anchor
        self.assertEqual(MemorySession(self.ui).aim.target,(80.,-12.))

    def test_native_key_overrides_and_explicit_unbinding_are_preserved(self):
        result=dict(resolve_bindings({26:(116,0),101:(323,0),31:(49,257)},
                                     {26:(59,0),101:(97,0),31:(0,0)}))
        self.assertEqual(result['net'],';')
        self.assertEqual(input_token(result['reel']),'key:a')
        self.assertNotIn('slot1',result)

    def test_feeder_handles_current_fish_before_another_rod(self):
        held=RodView('b','feeder',active=True,hooked=True,phase=RodPhase.HOOKED)
        other=RodView('c','feeder',hooked=True,phase=RodPhase.HOOKED)
        self.assertEqual(FeederStrategy().choose((other,held)).identity,'b')

    def test_spin_hook_interrupts_jig_pause_and_empty_line_resumes_pattern(self):
        now=[0.]
        strategy=SpinningStrategy(True,1.,2.,clock=lambda:now[0])
        rod=RodView('s','spinning')
        self.assertTrue(strategy.reeling(rod))
        now[0]=1.5
        self.assertFalse(strategy.reeling(rod))
        self.assertTrue(strategy.reeling(replace(rod,hooked=True)))

    def test_auto_mode_distinguishes_feeder_from_held_spin(self):
        feeder=RodView('f','feeder',on_rest=True)
        spin=RodView('s','spinning',active=True)
        self.assertEqual(resolve_mode('auto',(feeder,))[0],'feeder')
        self.assertEqual(resolve_mode('auto',(feeder,spin))[0],'spinning')
        with self.assertRaises(ValueError):resolve_mode('auto',(replace(spin,active=False),feeder))

    def test_feeder_preparation_starts_with_empty_hands(self):
        self.registry.update(1,[replace(self.rod,active=False,on_rest=True,phase=RodPhase.READY)])
        self.session.controller=Mock()
        with patch('saint_bait.runtime.log'):self.session.prepare()
        self.session.controller.start.assert_called_once()
        self.session.controller.wait_active.assert_not_called()
        self.session.controller.prepare.assert_called_once_with(None,None,['1'],on_ready=self.session.cast_ready)

    def test_overlay_is_compact_and_keeps_fish_weight(self):
        text=compact_line(replace(self.rod,slot_key='2',phase=RodPhase.HOOKED,hooked=True,
            species='tench',weight_g=2750,load_fraction=.63),{'tench':'Линь'})
        self.assertEqual(text,'2 · рыба · Линь · 2,75 кг · 63%')
        self.assertEqual(compact_line(RodView('x','feeder',phase=RodPhase.DEPLOYED),{}),'1 · ожидание')

    def test_overload_still_allows_confirmed_drag_reduction(self):
        from saint_bait.fight_control import FightDecision
        self.session.fight=Mock()
        self.session.fight.decide.return_value=FightDecision(-1,False,'снижаю нагрузку')
        self.session.controller.overload=Mock(return_value=True)
        rod=replace(self.rod,hooked=True,phase=RodPhase.HOOKED,line_m=20.,drag_setting=29)
        with patch('saint_bait.runtime.log'):self.session.retrieve(rod)
        self.session.input.adjust_drag.assert_called_once_with(-1)
        self.session.fight.sent.assert_called_once_with(rod,-1)
        self.session.input.hold.assert_not_called()

    def test_waiting_for_drag_ack_releases_inputs(self):
        from saint_bait.fight_control import FightDecision
        self.session.fight=Mock()
        self.session.fight.decide.return_value=FightDecision(waiting=True)
        self.session.retrieve(replace(self.rod,line_m=20.))
        self.session.input.release.assert_called_once()
        self.session.input.adjust_drag.assert_not_called()

    def test_net_uses_fish_distance_instead_of_line_counter(self):
        from saint_bait.fight_control import FightDecision
        self.registry.update_scene(SceneView(bindings=self.bindings))
        self.session.controller.overload=Mock(return_value=False)
        self.session.fight.decide=Mock(return_value=FightDecision())
        far=replace(self.rod,hooked=True,phase=RodPhase.HOOKED,line_m=1.,fish_distance=6.)
        self.session.retrieve(far)
        self.session.input.press.assert_not_called()
        self.session.input.hold.assert_any_call('reel',True)
        self.session.wait=Mock(return_value=True)
        self.session.input.token.return_value='t'
        with patch('saint_bait.runtime.log'):
            self.session.retrieve(replace(far,line_m=4.,fish_distance=2.5))
        self.session.input.press.assert_called_once_with('net')

    def test_early_net_is_stowed_before_continuing_to_reel(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,net_present=True))
        self.session.wait=Mock(return_value=True)
        self.session.retrieve(replace(self.rod,hooked=True,line_m=4.,fish_distance=6.))
        self.session.input.press.assert_called_once_with('net')
        self.session.input.hold.assert_not_called()

    def test_equipped_net_stops_winding_and_lifts_the_rod(self):
        from saint_bait.fight_control import FightDecision
        self.registry.update_scene(SceneView(bindings=self.bindings,net_present=True))
        self.session.controller.overload=Mock(return_value=False)
        self.session.fight.decide=Mock(return_value=FightDecision())
        self.session.retrieve(replace(self.rod,hooked=True,line_m=1.,fish_distance=2.5))
        self.session.input.hold.assert_any_call('reel',False)
        self.session.input.hold.assert_any_call('pull',True)
        self.session.input.press.assert_not_called()

    def test_lost_fish_stows_net_instead_of_lifting_forever(self):
        self.registry.update_scene(SceneView(bindings=self.bindings,net_present=True))
        self.session.wait=Mock(return_value=True)
        self.session.retrieve(replace(self.rod,hooked=False,phase=RodPhase.REEL_IN,line_m=1.))
        self.session.input.press.assert_called_once_with('net')
        self.session.input.hold.assert_not_called()

    def test_lost_resting_fish_is_retrieved_before_a_new_cast(self):
        now=[0.]
        strategy=FeederStrategy(clock=lambda:now[0])
        hooked=replace(self.rod,active=False,on_rest=True,hooked=True,phase=RodPhase.HOOKED)
        strategy.choose((hooked,))
        lost=replace(hooked,hooked=False,phase=RodPhase.DEPLOYED)
        ready=RodView('b','feeder',phase=RodPhase.READY)
        strategy.choose((ready,lost))
        now[0]=1.1
        self.assertEqual(strategy.choose((ready,lost)).identity,lost.identity)
        strategy.cast_finished(lost.identity)
        self.assertEqual(strategy.choose((ready,lost)).identity,'b')

    def test_short_fish_signal_gap_does_not_start_retrieval_or_recast(self):
        now=[0.]
        strategy=FeederStrategy(clock=lambda:now[0])
        hooked=replace(self.rod,hooked=True,phase=RodPhase.HOOKED)
        strategy.choose((hooked,))
        self.assertIsNone(strategy.choose((replace(hooked,hooked=False,phase=RodPhase.READY),)))
        now[0]=.5
        strategy.choose((hooked,))
        self.assertEqual(strategy.recast,set())

    def test_camera_restore_never_turns_with_hooked_fish(self):
        self.registry.update(1,[replace(self.rod,hooked=True,phase=RodPhase.HOOKED)])
        with patch('saint_bait.runtime.human_sleep'):
            with self.assertRaises(SessionCancelled):self.session.restore_cast_view(self.registry.snapshot()[0])
        self.session.input.move_view.assert_not_called()

    def test_select_refreshes_a_rod_that_was_put_on_rest_while_eating(self):
        previous=replace(self.rod,active=True)
        self.registry.update(1,[replace(self.rod,active=False,on_rest=True)])
        def take(key,urgent=False):self.registry.update(1,[replace(self.rod,active=True,on_rest=False)])
        self.session.controller.select=Mock(side_effect=take)
        self.assertTrue(self.session.select(previous).active)
        self.session.controller.select.assert_called_once_with('1',urgent=False)

    def test_shared_clip_is_applied_in_both_directions_and_verified(self):
        for initial in (6,10):
            self.session.input.reset_mock()
            self.registry.update(1,[replace(self.rod,phase=RodPhase.READY,clip_m=initial,drag_setting=29,drag_force=100.)])
            def adjust(direction):
                active=self.registry.snapshot()[0]
                self.registry.update(1,[replace(active,clip_m=active.clip_m+direction)])
            self.session.input.adjust_clip.side_effect=adjust
            with patch('saint_bait.runtime.log'):self.session.apply_rod_settings(self.registry.snapshot()[0])
            self.assertEqual(self.session.active().clip_m,8)
            self.assertEqual(self.session.input.adjust_clip.call_count,2)
            self.session.input.adjust_drag.assert_not_called()

    def test_matching_clip_and_safe_highest_unlocked_step_need_no_adjustment(self):
        self.registry.update(1,[replace(self.rod,phase=RodPhase.READY,clip_m=8,drag_setting=29,drag_force=100.)])
        with patch('saint_bait.runtime.log'):self.assertTrue(self.session.apply_rod_settings(self.registry.snapshot()[0]))
        self.session.input.adjust_clip.assert_not_called()
        self.session.input.adjust_drag.assert_not_called()

    def test_unconfirmed_clip_stops_before_cast(self):
        self.registry.update(1,[replace(self.rod,phase=RodPhase.READY,clip_m=7,drag_setting=29)])
        self.session.wait=Mock(side_effect=SessionCancelled('not confirmed'))
        with self.assertRaises(SessionCancelled):self.session.apply_rod_settings(self.registry.snapshot()[0])
        self.session.input.adjust_clip.assert_called_once_with(1)
        self.session.input.hold.assert_not_called()


if __name__=='__main__':unittest.main()
