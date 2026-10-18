"""Memory-only desktop startup; no real input or fishing threads."""
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from saint_bait.ui import SaintBaitUI
from saint_bait.telemetry.scene import SceneView


class AutomaticStartTests(unittest.TestCase):
    def fake_ui(self,scene=True):
        bindings=tuple(sorted(dict(reel='mouse:left',pull='mouse:right',net=';',stand='left alt',slot1='1').items()))
        return SimpleNamespace(_closing=False,_stopping=False,bot_thread=None,
            rod_registry=SimpleNamespace(scene=lambda:SceneView(bindings=bindings) if scene else None,
                snapshot=lambda:[SimpleNamespace(kind='feeder',active=False)]),
            fishing_mode='auto',_sync_game_controls=Mock(),_store_settings=Mock(),reset_session_stats=Mock(),
            _set_status=Mock(),stop_logic=Mock(),_run_engine=Mock(),btn_start=Mock(),btn_stop=Mock(),
            text=lambda key,*args:key)

    def test_start_needs_game_data_and_has_no_ocr_or_audio_branch(self):
        ui=self.fake_ui()
        with (patch('saint_bait.ui.keyboard.add_hotkey'),patch('saint_bait.ui.gw.getWindowsWithTitle',return_value=[Mock()]),
              patch('saint_bait.ui.is_game_focused',return_value=True),
              patch('saint_bait.ui.threading.Thread') as thread,patch('saint_bait.ui.engine.log')):
            SaintBaitUI.start_logic(ui)
        thread.return_value.start.assert_called_once_with()
        ui._set_status.assert_called_once_with('running')
        ui.stop_logic.assert_not_called()

    def test_own_bot_window_does_not_authorize_fishing_thread(self):
        ui=self.fake_ui()
        with (patch('saint_bait.ui.gw.getWindowsWithTitle',return_value=[Mock()]),
              patch('saint_bait.ui.is_game_focused',return_value=False),
              patch('saint_bait.ui.threading.Thread') as thread,patch('saint_bait.ui.engine.log')):
            SaintBaitUI.start_logic(ui)
        thread.assert_not_called()
        ui.stop_logic.assert_called_once()

    def test_missing_game_data_never_starts_fishing(self):
        ui=self.fake_ui(False)
        with patch('saint_bait.ui.threading.Thread') as thread,patch('saint_bait.ui.engine.log'):
            SaintBaitUI.start_logic(ui)
        thread.assert_not_called()
        ui._store_settings.assert_not_called()


if __name__=='__main__': unittest.main()
