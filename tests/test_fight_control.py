from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from saint_bait.fight_control import FightControl
from saint_bait.aim_control import CastAim,angle_delta
from saint_bait.rods import RodView,RodPhase
from saint_bait.telemetry.scene import SceneView
from saint_bait.bindings import resolve_bindings
from saint_bait.controls import SessionCancelled
from saint_bait.game_input import GameInput
from saint_bait.automatic_drag import BrakeProfile


class FightTests(unittest.TestCase):
    def setUp(self):
        self.now=0.
        self.control=FightControl(clock=lambda:self.now)
        self.control.set_brake_profile('a',BrakeProfile(((12,50.),(15,53.),(16,58.),(29,70.))))
        self.rod=RodView('a','feeder',active=True,hooked=True,memory_metrics=True,
            phase=RodPhase.HOOKED,line_m=20.,load_force=30.,tackle_limit=100.,
            drag_force=50.,drag_setting=15,drag_locked=False)

    def trend(self,rod,seconds=5.,metres_per_second=0.):
        for index in range(int(seconds*10)+1):
            self.now=index/10
            decision=self.control.decide(replace(rod,line_m=rod.line_m+self.now*metres_per_second))
            if decision.drag:return decision
        return decision

    def test_emergency_lowers_even_when_fast_guard_would_release(self):
        decision=self.control.decide(replace(self.rod,load_force=95.,drag_force=95.,drag_setting=29))
        self.assertEqual(decision.drag,-1)
        self.assertFalse(decision.lift)

    def test_locked_brake_is_unlocked_and_never_raised_to_30(self):
        self.assertEqual(self.control.decide(replace(self.rod,drag_locked=True,drag_force=None,drag_setting=30)).drag,-1)
        self.control.reset('a')
        self.assertEqual(self.trend(replace(self.rod,drag_setting=29,load_force=36.),metres_per_second=.2).drag,0)

    def test_payout_under_sustained_tension_can_raise_one_step(self):
        decision=self.trend(replace(self.rod,load_force=36.),metres_per_second=.2)
        self.assertEqual(decision.drag,1)

    def test_successful_retrieval_does_not_raise_drag(self):
        self.assertEqual(self.trend(replace(self.rod,load_force=36.),metres_per_second=-.5).drag,0)

    def test_low_tension_and_short_line_do_not_raise_drag(self):
        self.assertEqual(self.trend(self.rod,metres_per_second=.2).drag,0)
        self.control.reset('a')
        self.assertEqual(self.trend(replace(self.rod,line_m=4.,load_force=36.)).drag,0)

    def test_confirmation_is_required_and_does_not_repeat_input(self):
        rod=replace(self.rod,drag_force=95.,drag_setting=29)
        self.control.decide(rod)
        self.control.sent(rod,-1)
        self.now=.1
        decision=self.control.decide(rod)
        self.assertTrue(decision.waiting)
        self.assertEqual(decision.drag,0)
        self.now=2.1
        with self.assertRaises(SessionCancelled):self.control.decide(rod)

    def test_wrong_direction_is_detected(self):
        self.control.decide(self.rod)
        self.control.sent(self.rod,1)
        with self.assertRaises(SessionCancelled):self.control.decide(replace(self.rod,drag_setting=14))

    def test_acknowledged_adjustment_obeys_cooldown(self):
        self.control.decide(self.rod)
        self.control.sent(self.rod,1)
        raised=replace(self.rod,drag_setting=16,drag_force=55.)
        self.now=.1
        self.assertFalse(self.control.decide(raised).waiting)
        self.assertGreater(self.control.rods['a'].next_drag,5.)

    def test_rod_lift_is_bounded_and_released_on_tension_or_net(self):
        self.assertTrue(self.trend(self.rod,seconds=1.6).lift)
        self.now=1.7
        self.assertFalse(self.control.decide(replace(self.rod,load_force=40.)).lift)
        self.assertFalse(self.control.decide(self.rod,net=True).lift)

    def test_lift_releases_after_pulse_and_near_fish(self):
        self.assertTrue(self.trend(self.rod,seconds=1.6).lift)
        for index in range(17,29):
            self.now=index/10
            decision=self.control.decide(self.rod)
        self.assertFalse(decision.lift)
        self.assertFalse(self.control.decide(replace(self.rod,line_m=4.)).lift)

    def test_telemetry_gap_does_not_reuse_old_trend(self):
        self.trend(self.rod,seconds=1.6)
        self.now=10.
        self.assertFalse(self.control.decide(self.rod).lift)

    def test_missing_metrics_or_no_fish_does_not_adjust(self):
        for change in ({'load_force':None},{'hooked':False},{'active':False},{'drag_force':float('nan')}):
            decision=self.control.decide(replace(self.rod,**change))
            self.assertEqual((decision.drag,decision.lift),(0,False))

    def test_native_actions_resolve_drag_separately_from_reel_speed(self):
        bindings=dict(resolve_bindings({54:(270,61),55:(269,45),19:(114,0),52:(270,61)},{}))
        self.assertEqual((bindings['drag_up'],bindings['drag_down'],bindings['speed_modifier']),('add','subtract','r'))
        self.assertNotIn('reel_speed',bindings)

    def test_held_speed_modifier_blocks_drag_input(self):
        game=GameInput(None,dict(drag_up='add',drag_down='subtract',speed_modifier='r'))
        with patch('keyboard.is_pressed',return_value=True),patch('saint_bait.game_input.human_press') as press:
            with self.assertRaises(SessionCancelled):game.adjust_drag(1)
        press.assert_not_called()

    def test_drag_uses_native_alt_modifier_and_releases_it_after_failure(self):
        bindings=dict(resolve_bindings({54:(270,61),55:(269,45),19:(114,0)}, {}, {54:4,55:4,19:1}))
        self.assertEqual(bindings['drag_down_modifier'],'left alt')
        game=GameInput(None,bindings)
        with (patch('keyboard.is_pressed',return_value=False),
              patch('saint_bait.game_input.wait_for_focus',return_value=True),
              patch('saint_bait.game_input.check_running'),
              patch('saint_bait.game_input.human_press',side_effect=RuntimeError('input failed')),
              patch('pydirectinput.keyDown') as down,patch('pydirectinput.keyUp') as up):
            with self.assertRaises(RuntimeError):game.adjust_drag(-1)
        down.assert_called_once_with('altleft',_pause=False)
        up.assert_called_once_with('altleft',_pause=False)

    def test_stand_modifier_conflict_uses_single_unmodified_wheel_step(self):
        game=GameInput(None,dict(drag_up='add',drag_down='subtract',
            drag_down_modifier='left alt',stand='left alt',speed_modifier='r'))
        with (patch('keyboard.is_pressed',return_value=False),
              patch('saint_bait.game_input.wait_for_focus',return_value=True),
              patch('saint_bait.game_input.check_running'),
              patch('pyautogui.scroll') as wheel,
              patch('saint_bait.game_input.human_press') as press):
            game.adjust_drag(-1)
        wheel.assert_called_once_with(-1,_pause=False)
        press.assert_not_called()

    def test_explicit_net_key_is_used_without_changing_native_bindings(self):
        game=GameInput(None,{'net':';'},overrides={'net':'t'})
        with patch('saint_bait.game_input.human_press') as press:game.press('net')
        press.assert_called_once_with('t',None)
        self.assertEqual(game.bindings,{'net':';'})

    def test_automatic_profile_is_a_hard_ceiling(self):
        self.control.set_brake_profile('a',BrakeProfile(((12,50.),(13,90.))))
        self.assertEqual(self.control.decide(self.rod).drag,-1)
        self.control.reset('a')
        self.assertEqual(self.trend(replace(self.rod,drag_setting=12,load_force=36.),metres_per_second=.2).drag,0)

    def test_sparse_profile_does_not_keep_lowering_after_strength_drifts(self):
        self.control.set_brake_profile('a',BrakeProfile(((26,111.),(27,117.))))
        rod=replace(self.rod,drag_setting=26,drag_force=105.45,tackle_limit=129.,load_force=10.)
        self.assertEqual(self.control.decide(rod).drag,-1)
        self.control.sent(rod,-1)
        self.now=.1
        lower=replace(rod,drag_setting=25,drag_force=99.)
        self.assertEqual(self.control.decide(lower).drag,0)
        self.now=2.
        self.assertEqual(self.control.decide(lower).drag,0)

    def test_without_calibration_does_not_probe_higher_steps_on_fish(self):
        self.control=FightControl(clock=lambda:self.now)
        self.assertEqual(self.trend(replace(self.rod,load_force=36.),metres_per_second=.2).drag,0)


class AimTests(unittest.TestCase):
    def test_angle_wrap(self):
        self.assertEqual(angle_delta(1.,359.),2.)

    def test_feedback_converges_for_normal_and_inverted_mouse(self):
        for gains in ((.2,.2),(.2,-.2)):
            target=SceneView(camera_id='camera',camera_angles=(12.,-4.))
            aim=CastAim(target)
            current=replace(target,camera_angles=(20.,6.))
            for _ in range(16):
                move=aim.correction(current)
                if move==(0,0):break
                after=replace(current,camera_angles=tuple(v+p*g for v,p,g in zip(current.camera_angles,move,gains)))
                aim.observe(current,after,move)
                current=after
            self.assertEqual(aim.correction(current),(0,0))

    def test_no_mouse_response_cancels_cast(self):
        scene=SceneView(camera_id='camera',camera_angles=(1.,2.))
        with self.assertRaises(SessionCancelled):CastAim(scene).observe(scene,scene,(8,0))

    def test_camera_change_or_large_turn_cancels_cast(self):
        scene=SceneView(camera_id='camera',camera_angles=(1.,2.))
        aim=CastAim(scene)
        for value in (replace(scene,camera_id='other'),replace(scene,camera_angles=(150.,2.)),SceneView()):
            with self.assertRaises(SessionCancelled):aim.correction(value)


if __name__=='__main__':unittest.main()
