import unittest
from unittest.mock import patch
from types import SimpleNamespace
from saint_bait import controls, state


class ReleaseTests(unittest.TestCase):
    def tearDown(self): state.stop_event.clear()

    def test_mouse_release_works_with_stop_and_without_focus(self):
        state.stop_event.set()
        with patch.object(controls,'wait_for_focus') as focus, patch.object(controls.pyautogui,'mouseUp') as up:
            controls.safe_mouse('up','left')
        focus.assert_not_called()
        up.assert_called_once_with(button='left',_pause=True)

    def test_stopping_during_key_hold_always_releases_key(self):
        state.stop_event.clear()
        with (patch.object(controls,'wait_for_focus',return_value=True),
              patch.object(controls.pydirectinput,'keyDown',side_effect=lambda key:state.stop_event.set()),
              patch.object(controls.pydirectinput,'keyUp') as up):
            with self.assertRaises(controls.SessionCancelled): controls.human_press('1')
        up.assert_called_once_with('1')

    def test_stop_blocks_new_mouse_down(self):
        state.stop_event.set()
        with patch.object(controls.pyautogui,'mouseDown') as down:
            with self.assertRaises(controls.SessionCancelled): controls.safe_mouse('down','left')
        down.assert_not_called()

    def test_game_modifier_names_are_converted_before_physical_input(self):
        state.stop_event.clear()
        with (patch.object(controls,'wait_for_focus',return_value=True),
              patch.object(controls.pydirectinput,'keyDown') as down,
              patch.object(controls.pydirectinput,'keyUp') as up,
              patch.object(controls.state.stop_event,'wait',return_value=False)):
            controls.human_press('left alt')
        down.assert_called_once_with('altleft')
        up.assert_called_once_with('altleft')

    def test_stop_interrupts_long_sleep(self):
        state.stop_event.set()
        with self.assertRaises(controls.SessionCancelled): controls.human_sleep(3600)

    def test_focus_loss_stops_and_releases_an_active_session(self):
        state.stop_event.clear()
        guard=controls.FocusGuard(None)
        with (patch.object(controls.gw,'getActiveWindow',side_effect=[SimpleNamespace(title=controls.game_title),None]),
              patch.object(controls,'release_all') as release,patch.object(controls,'log')):
            guard.check_once()
            self.assertFalse(state.stop_event.is_set())
            guard.check_once()
        self.assertTrue(state.stop_event.is_set())
        release.assert_called_once_with(None)

    def test_own_bot_title_is_never_accepted_as_game_focus(self):
        self.assertFalse(controls.is_game_focused(SimpleNamespace(title='Saint Bait · '+controls.game_title)))

    def test_legacy_break_sleep_is_also_interruptible(self):
        from saint_bait.timing import game_time
        state.stop_event.set()
        with self.assertRaises(controls.SessionCancelled): game_time.sleep(7200)


if __name__=='__main__': unittest.main()
