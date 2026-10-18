import time


class SpinningStrategy:
    name='spinning'

    def __init__(self,jig=False,reel_s=1.42,pause_s=2.58,clock=time.monotonic):
        self.jig,self.reel_s,self.pause_s=jig,reel_s,pause_s
        self.clock=clock
        self._cycle_start=None

    def choose(self,rods):
        return next((rod for rod in rods if rod.active),None)

    def reeling(self,rod):
        if rod.hooked or not self.jig:
            self._cycle_start=None
            return True
        if self._cycle_start is None:
            self._cycle_start=self.clock()
        return (self.clock()-self._cycle_start)%(self.reel_s+self.pause_s)<self.reel_s
