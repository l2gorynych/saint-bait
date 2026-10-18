"""Decide when food is useful from measured nutrition, not elapsed fishing time."""
import math
import random


class FoodControl:
    def __init__(self,uniform=random.uniform):
        self.uniform=uniform
        self._new_cycle()
        self.recovering=False
        self.last_gain=None
        self.retry_after=0.

    def _new_cycle(self):
        self.trigger=self.uniform(.30,.42)
        self.target=self.uniform(.70,.80)

    def _finish(self):
        if self.recovering:
            self.recovering=False
            self._new_cycle()

    def needs_food(self,satiety,now):
        if satiety is None or not math.isfinite(satiety) or not 0<=satiety<=1:return False
        if satiety>=self.target:self._finish()
        if satiety<=self.trigger:self.recovering=True
        if self.last_gain and satiety>.5 and satiety+self.last_gain>1.02:
            self._finish()
        return self.recovering and now>=self.retry_after

    def portions_needed(self,satiety):
        if self.last_gain is None or satiety is None:return None
        if satiety>=self.target:return 0
        if satiety>.5 and satiety+self.last_gain>1.02:return 0
        return max(0,math.ceil((self.target-satiety)/self.last_gain))

    def measured(self,before,after,now):
        gain=after-before
        if gain>=.01:
            self.last_gain=gain if self.last_gain is None or abs(gain-self.last_gain)>.5*self.last_gain else .6*self.last_gain+.4*gain
            self.retry_after=now+self.uniform(2.,4.)
            if after>=self.target:self._finish()
            return gain
        self.retry_after=now+90.
        return None
