import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from saint_bait.food_control import FoodControl
from saint_bait.auxiliary import AuxiliaryActions


class FoodTests(unittest.TestCase):
    def food(self):return FoodControl(uniform=lambda low,high:(low+high)/2)
    def test_low_satiety_triggers_without_waiting_ten_minutes(self):
        food=self.food()
        self.assertTrue(food.needs_food(.1,0.))
        self.assertEqual(food.measured(.1,.3,1.),.19999999999999998)
        self.assertTrue(food.needs_food(.3,4.))
        self.assertTrue(food.needs_food(.55,4.))
        self.assertFalse(food.needs_food(.8,4.))

    def test_no_recovery_prevents_food_spam(self):
        food=self.food()
        self.assertTrue(food.needs_food(.1,0.))
        self.assertIsNone(food.measured(.1,.1,1.))
        self.assertFalse(food.needs_food(.1,30.))

    def test_missing_values_do_not_consume_food(self):
        food=self.food()
        for value in (None,float('nan'),-.1,1.5,.7):
            self.assertFalse(food.needs_food(value,0.))

    def test_remaining_portions_follow_actual_recovery(self):
        food=self.food()
        self.assertIsNone(food.portions_needed(.1))
        food.measured(.1,.3,0.)
        self.assertEqual(food.portions_needed(.3),3)
        self.assertEqual(food.portions_needed(.8),0)

    def test_large_portion_is_not_wasted_when_already_well_fed(self):
        food=self.food()
        food.needs_food(.1,0.)
        food.measured(.1,.65,0.)
        self.assertFalse(food.needs_food(.65,10.))
        self.assertEqual(food.portions_needed(.65),0)

    def test_threshold_stays_fixed_until_the_current_cycle_finishes(self):
        values=iter((.31,.72,2.5,.41,.79))
        food=FoodControl(uniform=lambda low,high:next(values))
        self.assertFalse(food.needs_food(.32,0.))
        self.assertTrue(food.needs_food(.30,0.))
        self.assertTrue(food.needs_food(.5,0.))
        self.assertEqual(food.trigger,.31)
        food.measured(.5,.75,0.)
        self.assertEqual((food.trigger,food.target),(.41,.79))

    def test_preparing_a_cast_does_not_interrupt_it_for_food(self):
        actions=AuxiliaryActions.__new__(AuxiliaryActions)
        actions.ui=SimpleNamespace(check_auto_flashlight=Mock(get=lambda:False),check_stop_at_night=Mock(get=lambda:False))
        actions.idle=Mock()
        actions.before_cast()
        actions.idle.assert_not_called()


if __name__=='__main__':unittest.main()
