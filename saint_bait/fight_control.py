"""Feedback decisions for one fish; no input, UI or game-memory writes."""
from collections import deque
from dataclasses import dataclass,field
import math
import time
from .automatic_drag import SAFETY_FRACTION,worst_force


@dataclass(frozen=True)
class FightDecision:
    drag: int = 0
    lift: bool = False
    reason: str = ''
    waiting: bool = False


@dataclass
class FightHistory:
    samples: deque = field(default_factory=deque)
    pending: tuple | None = None
    next_drag: float = 0.
    lift_until: float = 0.
    next_lift: float = 0.
    forces: dict = field(default_factory=dict)


class FightControl:
    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.rods={}
        self.brakes={}

    def set_brake_profile(self,identity,profile):
        self.brakes[identity]=profile

    def reset(self,identity):
        self.rods.pop(identity,None)

    def decide(self,rod,*,net=False):
        from .controls import SessionCancelled
        now=self.clock()
        values=(rod.load_force,rod.tackle_limit,rod.line_m)
        if (not rod.active or not rod.hooked or not rod.memory_metrics or
                any(v is None or not math.isfinite(v) or v<0 for v in values) or
                rod.tackle_limit<=0 or not isinstance(rod.drag_setting,int) or
                not 1<=rod.drag_setting<=30):
            self.reset(rod.identity)
            return FightDecision()
        history=self.rods.setdefault(rod.identity,FightHistory())
        if history.samples and now-history.samples[-1][0]>.6:
            # Never act on a trend spanning a focus/telemetry gap or another rod.
            history.samples.clear()
            history.lift_until=0.
        history.samples.append((now,rod.line_m,rod.load_force))
        while history.samples and now-history.samples[0][0]>6:
            history.samples.popleft()
        if history.pending:
            old,direction,deadline=history.pending
            if rod.drag_setting!=old:
                if rod.drag_setting!=old+direction:
                    raise SessionCancelled('Фрикцион изменился неожиданно; проверьте управление')
                history.pending=None
                history.next_drag=now+(.18 if direction<0 else 5.)
            elif now>=deadline:
                raise SessionCancelled('Изменение фрикциона не подтверждено игрой')
            else:
                return FightDecision(waiting=True)
        locked=rod.drag_locked is True
        drag=rod.drag_force
        if not locked and (rod.drag_locked is not False or drag is None or not math.isfinite(drag) or drag<=0):
            return FightDecision()
        force,strength=rod.load_force,rod.tackle_limit
        ceiling=strength if locked else min(strength,drag)
        if not locked:history.forces[rod.drag_setting]=drag
        profile=self.brakes.get(rod.identity)
        # An empty safe subset means the measured profile does not include a
        # lower step yet. Zero is not a brake limit: the actual current force
        # decides whether to lower again after the first acknowledged step.
        max_drag=(profile.maximum(strength) or rod.drag_setting) if profile is not None else rod.drag_setting
        span=now-history.samples[0][0]
        delta=rod.line_m-history.samples[0][1]
        peak=max(sample[2] for sample in history.samples)
        # Lower first, even if the fast input guard already released winding.
        if now>=history.next_drag and rod.drag_setting>1 and (
                rod.drag_setting>max_drag or locked or worst_force(rod)>SAFETY_FRACTION*strength or force>.9*strength):
            history.lift_until=0.
            return FightDecision(-1,False,'снижаю нагрузку')
        # Raise only when the fish is taking line / not coming closer under
        # sustained tension, with enough room for the next step. Never lock 30.
        next_force=profile.force_at(rod.drag_setting+1) if profile is not None else None
        if (not locked and next_force is not None and now>=history.next_drag and span>=4. and
                rod.drag_setting<min(29,max_drag) and rod.line_m>6. and delta>=-.1 and
                force>=.65*drag and peak<.72*strength and next_force<=SAFETY_FRACTION*strength):
            history.lift_until=0.
            return FightDecision(1,False,'добавляю тормоз')
        # A short pump is useful when the line has stopped coming in. Near the
        # net or under high tension the rod must be lowered immediately.
        landing_lift=(rod.fish_distance is not None and 3.<rod.fish_distance<8. and rod.line_m<=6.)
        can_lift=(not net and (rod.line_m>6. or landing_lift) and force<.72*ceiling and
                  span>=1.5 and delta>-.25)
        if not can_lift:
            history.lift_until=0.
        elif now>=history.next_lift and now>=history.lift_until:
            history.lift_until=now+(2.0 if landing_lift else 1.1)
            history.next_lift=now+3.5
        return FightDecision(lift=can_lift and now<history.lift_until)

    def sent(self,rod,direction):
        """Arm an acknowledgement only after input was actually sent."""
        history=self.rods[rod.identity]
        history.pending=(rod.drag_setting,direction,self.clock()+2.)
        history.samples.clear()
        history.lift_until=0.
