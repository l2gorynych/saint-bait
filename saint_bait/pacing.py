"""Bounded variation for ordinary actions; observation and protection stay fast."""
import random


class ActionPacing:
    RANGES = {'settle':(.32,.66,.43), 'select':(.16,.42,.23),
              'bite':(.18,.58,.29), 'before_cast':(.22,.62,.35),
              'pickup':(.9,1.3,1.1)}

    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.tempo = self.rng.uniform(.94,1.06)

    def delay(self, action, urgent=False):
        if urgent:
            return 0.
        self.tempo=min(1.06,max(.94,self.tempo+self.rng.uniform(-.008,.008)))
        low,high,mode = self.RANGES[action]
        return min(high,max(low,self.rng.triangular(low,high,mode)*self.tempo))
