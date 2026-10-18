"""Dynamic reel-force limits and prompt release of requested fishing inputs."""
import math
import threading
from . import state
from .controls import SessionCancelled
from .rods import RodPhase


RELEASE_MARGIN = .97
RESUME_MARGIN = .88


def load_limits(rod):
    """Both forces use the client's internal force units, never brake clicks."""
    current, strength = rod.load_force, rod.tackle_limit
    if (current is None or strength is None or not math.isfinite(current)
            or not math.isfinite(strength) or current < 0 or strength <= 0):
        raise ValueError('Нет достоверного значения нагрузки снасти')
    if rod.drag_locked is True:
        # At setting 30 the client uses FLT_MAX: the brake no longer limits force.
        ceiling = strength
    elif rod.drag_locked is False and rod.drag_force is not None:
        if not math.isfinite(rod.drag_force) or rod.drag_force <= 0:
            raise ValueError('Недостоверное усилие фрикциона')
        ceiling = min(strength, rod.drag_force)
    else:
        raise ValueError('Нет достоверного усилия фрикциона')
    return ceiling*RELEASE_MARGIN, ceiling*RESUME_MARGIN


class LoadInputGuard:
    """Recheck held input even while the fishing worker waits or moves camera.

    Only inputs explicitly requested by the fishing worker may resume. An up,
    Stop, missing rod or failure clears them; the guard never picks a new action.
    """
    def __init__(self, controller, buttons, down, up):
        self.controller = controller
        self.buttons = frozenset(buttons)
        self.down, self.up = down, up
        self._requested, self._held = set(), set()
        self._lock = threading.RLock()
        self._done = threading.Event()
        self._worker = None
        self._identity = None
        self._casting = False

    def start(self):
        self._worker = threading.Thread(target=self._run,name='SaintBait-LoadGuard',daemon=True)
        self._worker.start()

    def request(self, action, button):
        if button not in self.buttons or action not in ('up','down'):
            return False
        with self._lock:
            if action == 'up':
                self._requested.discard(button)
                self._held.discard(button)
                self.up(button=button,_pause=False)
            else:
                if state.stop_event.is_set() or self._done.is_set():
                    raise SessionCancelled('Рыбалка остановлена')
                self._requested.add(button)
                try:
                    self.refresh()
                except Exception:
                    self._release()
                    raise
        return True

    def _release(self):
        self._requested.clear()
        for button in tuple(self._held):
            self.up(button=button,_pause=False)
            self._held.discard(button)
        self._identity = None
        self._casting = False

    def refresh(self):
        with self._lock:
            if state.stop_event.is_set() or self._done.is_set():
                self._release()
                return
            if not self._requested:
                self._identity = None
                self._casting = False
                return
            rod = self.controller.active(max_age=.3)
            if rod is None or rod.phase==RodPhase.UNKNOWN:
                raise SessionCancelled('Потеряны свежие данные снасти; подмотка остановлена')
            if self._identity is not None and self._identity!=rod.identity:
                self._release()
                raise SessionCancelled('Снасть сменилась во время удержания кнопки')
            if self._identity is None:
                self._casting = bool(state.is_casting)
            if rod.phase==RodPhase.CATCH or (rod.phase==RodPhase.READY and not self._casting):
                self._release()
                return
            self._identity = rod.identity
            blocked = self.controller.overload()
            desired = set() if blocked else set(self._requested)
            for button in self._held-desired:
                self.up(button=button,_pause=False)
            self._held.intersection_update(desired)
            for button in desired-self._held:
                if state.stop_event.is_set() or self._done.is_set():
                    self._release()
                    return
                self.down(button=button,_pause=False)
                self._held.add(button)

    def stop(self):
        self._done.set()
        with self._lock:
            self._release()
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=.3)

    def _run(self):
        try:
            while not self._done.wait(.05) and not state.stop_event.is_set():
                self.refresh()
        except Exception as error:
            state.stop_event.set()
            from .logging_utils import log
            log(str(error),self.controller.ui)
        finally:
            with self._lock:
                self._release()
