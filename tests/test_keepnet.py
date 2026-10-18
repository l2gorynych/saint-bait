import unittest
from types import SimpleNamespace
from saint_bait.keepnet import parse_keepnet,keepnet_full
from saint_bait.telemetry.scene import SceneView


class KeepnetTests(unittest.TestCase):
    def test_native_hud_count_and_capacity(self):
        self.assertEqual(parse_keepnet('30 / 100'),(30,100))
        self.assertEqual(parse_keepnet('0/50'),(0,50))
        self.assertEqual(parse_keepnet('150 / 150'),(150,150))
        self.assertTrue(keepnet_full(SceneView(keepnet_count=100,keepnet_capacity=100)))
        self.assertFalse(keepnet_full(SceneView(keepnet_count=99,keepnet_capacity=100)))

    def test_absent_or_invalid_values_are_unknown_not_an_empty_keepnet(self):
        for text in (None,'','? / 100','101/100','-1/100','1/0','1/10001','other 30/100'):
            self.assertEqual(parse_keepnet(text),(None,None))
        self.assertFalse(keepnet_full(SceneView()))
