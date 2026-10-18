"""Find the greatest observed safe brake step on an unloaded, ready rig."""
import math
from dataclasses import dataclass
from .rods import RodPhase


SAFETY_FRACTION=.85


def checked_strength(rod):
    if rod.tackle_limit is None or not math.isfinite(rod.tackle_limit) or rod.tackle_limit<=0:
        raise ValueError('Нет достоверного предела снасти')
    return rod.tackle_limit


def worst_force(rod):
    """Reserve the reel's entire 5% heat correction, including later cooling."""
    if rod.drag_force is None or not math.isfinite(rod.drag_force) or rod.drag_force<=0:
        raise ValueError('Нет достоверного усилия тормоза')
    return rod.drag_force/.95


@dataclass(frozen=True)
class BrakeProfile:
    forces: tuple

    def maximum(self,strength):
        return max((step for step,force in self.forces if force<=strength*SAFETY_FRACTION),default=0)

    def force_at(self,step):
        return dict(self.forces).get(step)


class BrakeCalibration:
    def __init__(self,identity):
        self.identity=identity
        self.forces={}

    def observe(self,rod):
        if rod.identity!=self.identity or not rod.active or rod.hooked or rod.phase!=RodPhase.READY:
            raise ValueError('Настройка тормоза разрешена только на свободной снасти')
        strength=checked_strength(rod)
        if rod.load_force is None or not math.isfinite(rod.load_force) or not 0<=rod.load_force<strength*.1:
            raise ValueError('Снасть нагружена; подбор фрикциона отменён')
        if not isinstance(rod.drag_setting,int) or not 1<=rod.drag_setting<=30:
            raise ValueError('Нет деления фрикциона')
        if rod.drag_locked is True:return -1
        if rod.drag_locked is not False:raise ValueError('Нет состояния тормоза')
        step=rod.drag_setting
        force=worst_force(rod)
        self.forces[step]=force
        ceiling=strength*SAFETY_FRACTION
        if force>ceiling:
            if step==1:raise ValueError('Даже минимальный тормоз превышает безопасное усилие снасти')
            return -1
        if step==29:return 0
        next_force=self.forces.get(step+1)
        if next_force is not None and next_force>ceiling:return 0
        return 1

    def profile(self):
        return BrakeProfile(tuple(sorted(self.forces.items())))
