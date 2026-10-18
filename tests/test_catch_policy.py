import unittest
from unittest.mock import patch
from saint_bait.catch_policy import release_small
from saint_bait.game_input import GameInput


class CatchPolicyTests(unittest.TestCase):
    def test_only_confirmed_small_fish_without_awards_are_released(self):
        self.assertTrue(release_small(1,False,False,roll=lambda:.1))
        self.assertFalse(release_small(1,False,False,roll=lambda:.9))
        for grade in (None,0,2,3,4):self.assertFalse(release_small(grade,False,False,roll=lambda:0.))
        for trophy,card in ((True,False),(False,True),(None,False),(False,None)):
            self.assertFalse(release_small(1,trophy,card,roll=lambda:0.))

    def test_repeated_hold_and_release_do_not_spam_game_input(self):
        game=GameInput(None,dict(reel='mouse:left',pull='mouse:right'))
        with patch('saint_bait.game_input.safe_mouse') as send:
            for _ in range(20):game.hold('reel',True)
            for _ in range(20):game.release()
        self.assertEqual([call.args[:2] for call in send.call_args_list],[('down','left'),('up','left')])
