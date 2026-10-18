"""Restore the initial casting view using observed angular feedback."""
import math
from .controls import SessionCancelled


def angle_delta(target,current):
    return (target-current+180.)%360.-180.


class CastAim:
    def __init__(self,scene):
        self.identity=scene.camera_id
        self.target=scene.camera_angles
        self.gains=[None,None]

    def correction(self,scene):
        if (not self.identity or self.target is None or scene.camera_id!=self.identity or
                scene.camera_angles is None):
            raise SessionCancelled('Направление камеры недоступно; заброс отменён')
        errors=(angle_delta(self.target[0],scene.camera_angles[0]),self.target[1]-scene.camera_angles[1])
        if any(not math.isfinite(v) or abs(v)>100 for v in errors):
            raise SessionCancelled('Камера сильно смещена; проверьте место заброса')
        if all(abs(v)<=.6 for v in errors):return (0,0)
        result=[]
        for error,gain in zip(errors,self.gains):
            if abs(error)<=.6:result.append(0)
            elif gain is None:result.append(8 if error>0 else -8)
            else:result.append(round(max(-60,min(60,error/gain*.75))) or (1 if error/gain>0 else -1))
        return tuple(result)

    def observe(self,before,after,movement):
        if before.camera_id!=after.camera_id or before.camera_angles is None or after.camera_angles is None:
            raise SessionCancelled('Камера сменилась; заброс отменён')
        changes=(angle_delta(after.camera_angles[0],before.camera_angles[0]),
                 after.camera_angles[1]-before.camera_angles[1])
        for axis,(pixels,change) in enumerate(zip(movement,changes)):
            if not pixels:continue
            gain=change/pixels
            if not .002<=abs(gain)<=5:
                raise SessionCancelled('Поворот камеры не подтверждён; заброс отменён')
            previous=self.gains[axis]
            if previous is not None and (gain*previous<=0 or abs(gain/previous)>3):
                raise SessionCancelled('Управление камерой изменилось; заброс отменён')
            self.gains[axis]=gain if previous is None else .5*(gain+previous)
