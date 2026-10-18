from ..rods import RodPhase
import time


class FeederStrategy:
    name='feeder'

    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.attached=set()
        self.recast=set()
        self.missing_since={}

    def cast_finished(self,identity):
        self.recast.discard(identity)
        self.attached.discard(identity)
        self.missing_since.pop(identity,None)

    def choose(self,rods):
        hooked={rod.identity for rod in rods if rod.hooked}
        present={rod.identity for rod in rods}
        results={rod.identity for rod in rods if rod.phase==RodPhase.CATCH}
        self.recast.intersection_update(present)
        self.attached.intersection_update(present-results)
        self.attached.update(hooked)
        for identity in list(self.missing_since):
            if identity not in present or identity in hooked|results:self.missing_since.pop(identity)
        now=self.clock()
        uncertain=set()
        for identity in self.attached-hooked-results:
            since=self.missing_since.setdefault(identity,now)
            if now-since<1.0:uncertain.add(identity)
            else:
                self.recast.add(identity)
                self.attached.discard(identity)
                self.missing_since.pop(identity,None)
        self.recast.difference_update(hooked|results)
        # Finish the fish already in hand before picking another feeder up.
        return (next((rod for rod in rods if rod.active and rod.phase==RodPhase.CATCH),None)
                or next((rod for rod in rods if rod.active and rod.hooked),None)
                or next((rod for rod in rods if rod.hooked),None)
                or next((rod for rod in rods if rod.active and rod.identity not in uncertain and rod.phase in (RodPhase.READY,RodPhase.REEL_IN)),None)
                or next((rod for rod in rods if rod.identity in self.recast),None)
                or next((rod for rod in rods if rod.identity not in uncertain and rod.phase==RodPhase.READY),None))
