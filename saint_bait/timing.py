"""Game-loop clock: retain existing durations, make every wait cancellable."""
import time as _clock
from . import state
from .controls import SessionCancelled


class GameClock:
    time = staticmethod(_clock.time)
    monotonic = staticmethod(_clock.monotonic)
    strftime = staticmethod(_clock.strftime)

    @staticmethod
    def sleep(seconds):
        if seconds < 0:
            raise ValueError('sleep length must be non-negative')
        if state.stop_event.wait(seconds):
            raise SessionCancelled('Рыбалка остановлена')


game_time = GameClock()
