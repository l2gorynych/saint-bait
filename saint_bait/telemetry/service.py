"""One cancellable read-only worker; absent games and stale data are explicit."""
import threading
from .reader import Reader
from .observer import TackleObserver
from .scene import SceneObserver
from ..catch_journal import JournalWorker


class RodMonitor:
    def __init__(self, registry, journal=None):
        self.registry = registry
        self.journal_worker=JournalWorker(journal) if journal else None
        self._stop = threading.Event()
        self._worker = None

    def start(self):
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        if self.journal_worker:self.journal_worker.start()
        self._worker = threading.Thread(target=self._run,name='SaintBait-RodMonitor',daemon=True)
        self._worker.start()

    def stop(self):
        self._stop.set()
        if self.journal_worker:self.journal_worker.stop()

    @property
    def journal_error(self):return self.journal_worker.error if self.journal_worker else None

    def _run(self):
        while not self._stop.is_set():
            try:
                with Reader() as reader:
                    observer = TackleObserver(reader)
                    scene_reader = SceneObserver(observer)
                    while not self._stop.is_set():
                        items = observer.read()
                        self.registry.update((reader.pid,reader.base,observer.scene_identity),items)
                        if observer.scene_identity is not None:
                            scene=scene_reader.read(observer.game_controller,observer.scene_identity)
                            self.registry.update_scene(scene)
                            if self.journal_worker is not None:
                                self.journal_worker.submit(scene,items,(reader.pid,reader.base,observer.scene_identity))
                        if observer.scene_identity is None:
                            self.registry.unavailable('Игровая сцена ещё не загружена')
                        self._stop.wait(.05 if any(item.active for item in items) else .25)
            except (OSError,ValueError,StopIteration,RuntimeError,KeyError):
                self.registry.unavailable('Нет данных игры · повторное подключение')
                self._stop.wait(2)
