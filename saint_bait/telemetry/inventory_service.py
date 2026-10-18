"""A separate slow observer keeps inventory/price work out of load protection."""
import threading
from .reader import Reader
from .observer import TackleObserver
from .scene import SceneObserver
from .inventory import InventoryObserver


class InventoryMonitor:
    def __init__(self,registry,journal):
        self.registry=registry;self.journal=journal
        self._stop=threading.Event();self._thread=None
        self.error=None

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear()
        self._thread=threading.Thread(target=self._run,name='SaintBait-Inventory',daemon=True)
        self._thread.start()

    def stop(self):self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                with Reader() as reader:
                    observer=TackleObserver(reader);inventory=InventoryObserver(observer)
                    while not self._stop.is_set():
                        observer.read()
                        if observer.scene_identity is not None:
                            scene=self.registry.scene()
                            self.registry.update_corf(inventory.corf())
                            prices=inventory.prices(observer.game_controller,scene.waterbody_id) if scene else ()
                            if prices:self.journal.add_prices(prices)
                            self.error=None
                        self._stop.wait(2)
            except (OSError,ValueError,StopIteration,RuntimeError,KeyError):
                self.error='Данные садка пока недоступны'
                self.registry.update_corf(())
                self._stop.wait(3)
