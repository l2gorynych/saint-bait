"""Thread-safe tackle model, independent of widgets, Windows input and OCR."""
from dataclasses import dataclass, replace
from enum import StrEnum
import math
import threading
import time
import json
from pathlib import Path


class RodPhase(StrEnum):
    UNKNOWN = 'unknown'
    READY = 'ready'
    DEPLOYED = 'deployed'
    REEL_IN = 'reel_in'
    HOOKED = 'hooked'
    CATCH = 'catch'
    CASTING = 'casting'


PHASE_TEXT = {
    RodPhase.UNKNOWN: 'Проверяем снасть', RodPhase.READY: 'Можно забрасывать',
    RodPhase.DEPLOYED: 'Заброшена · ждём рыбу', RodPhase.REEL_IN: 'Нужно докрутить',
    RodPhase.HOOKED: 'Рыба на крючке · вываживать', RodPhase.CATCH: 'Рыба доставлена',
    RodPhase.CASTING: 'Выполняется заброс',
}


def classify_screen(*, fish, catch, distance, on_rest=False):
    if catch:
        return RodPhase.CATCH
    if fish:
        return RodPhase.HOOKED
    # Historical OCR sentinel is never evidence of an empty/ready rod.
    if (isinstance(distance, bool) or not isinstance(distance, (int, float))
            or not math.isfinite(distance) or distance == 999 or distance < 0):
        return RodPhase.UNKNOWN
    if distance == 0:
        return RodPhase.READY
    return RodPhase.DEPLOYED if on_rest else RodPhase.REEL_IN


def classify_memory(*, code, pending, hooked, active, on_rest):
    if pending:
        return RodPhase.CATCH, False
    if hooked:
        return RodPhase.HOOKED, True
    # FishingSet.fkfggbmbfij (RVA 0x5D8F50) tests code == 0 && !pending.
    if code == 0:
        return RodPhase.READY, False
    if code == 1:
        return RodPhase.CASTING, None
    if code in (2,3):
        return (RodPhase.DEPLOYED if on_rest else RodPhase.REEL_IN if active else RodPhase.UNKNOWN), True
    return RodPhase.UNKNOWN, None


@dataclass(frozen=True)
class RodView:
    identity: str
    kind: str
    slot_key: str | None = None
    active: bool = False
    on_rest: bool = False
    hooked: bool = False
    species: str | None = None
    weight_g: int | None = None
    phase: RodPhase = RodPhase.UNKNOWN
    cast: bool | None = None
    updated: float = 0.
    memory_metrics: bool = False
    state_code: int | None = None
    line_m: float | None = None
    load_fraction: float | None = None
    load_force: float | None = None
    tackle_limit: float | None = None
    drag_force: float | None = None
    drag_setting: int | None = None
    drag_locked: bool | None = None
    clip_m: int | None = None
    grade: int | None = None
    fish_distance: float | None = None
    equipment: tuple = ()


class RodRegistry:
    def __init__(self, clock=time.monotonic,cache_path=None):
        self._clock = clock
        self._lock = threading.RLock()
        self._items = {}
        self._known = {}
        self._generation = None
        self.error = 'Ожидание игры'
        self._observed_at = None
        self._scene = None
        self._cache_path=Path(cache_path) if cache_path else None
        self._corf=()
        self._corf_at=None

    def update_corf(self,items):
        with self._lock:self._corf=tuple(items);self._corf_at=self._clock()

    def corf(self,max_age=6):
        with self._lock:
            return self._corf if self._corf_at is not None and self._clock()-self._corf_at<=max_age else ()

    def update(self, generation, items):
        now = self._clock()
        with self._lock:
            if generation != self._generation:
                self._items.clear()
                self._known.clear()
                self._generation = generation
                self._scene = None
                if self._cache_path and isinstance(generation,tuple):
                    try:
                        if self._cache_path.stat().st_size<=16384:
                            saved=json.loads(self._cache_path.read_text(encoding='utf-8'))
                            rows=saved.get('rods',[])
                            if saved.get('generation')==list(generation) and len(rows)<=16:
                                keys=[row['key'] for row in rows]
                                if len(keys)==len(set(keys)) and all(isinstance(key,str) and 0<len(key)<32 for key in keys):
                                    self._known={row['identity']:RodView(row['identity'],row['kind'],slot_key=row['key'],updated=now) for row in rows}
                    except (OSError,ValueError,KeyError,TypeError):pass
            result = {}
            for item in items:
                previous = self._known.get(item.identity)
                if previous:
                    item = replace(item, slot_key=previous.slot_key)
                    if item.phase==RodPhase.CATCH and item.species is None and previous.phase in (RodPhase.HOOKED,RodPhase.CATCH):
                        item=replace(item,species=previous.species,weight_g=previous.weight_g,grade=previous.grade)

                    if not item.memory_metrics:
                        item = replace(item,cast=previous.cast,phase=previous.phase)
                if item.memory_metrics:
                    pass
                elif item.hooked:
                    item = replace(item, phase=RodPhase.HOOKED, cast=True)
                elif previous and previous.hooked:
                    item = replace(item, phase=RodPhase.UNKNOWN, cast=None)
                elif item.on_rest and item.cast is True:
                    item = replace(item, phase=RodPhase.DEPLOYED)
                elif item.active and item.cast is True and item.phase == RodPhase.DEPLOYED:
                    item = replace(item, phase=RodPhase.REEL_IN)
                result[item.identity] = self._catch_view(replace(item, updated=now),self._scene)
            self._items = result
            self._observed_at = now
            # Pick-up animations briefly remove a rod from BOTH game fields.
            # Keep its binding, but never expose an absent rod as fresh data.
            self._known = {key:value for key,value in self._known.items()
                           if 0 <= now-value.updated <= 10}
            self._known.update(result)
            self.error = ''

    def unavailable(self, reason):
        with self._lock:
            self.error = reason

    def update_scene(self,scene):
        with self._lock:
            self._scene=scene
            self._items={identity:self._catch_view(item,scene) for identity,item in self._items.items()}
            self._known.update(self._items)

    @staticmethod
    def _catch_view(item,scene):
        if (item.active and scene is not None and scene.catch_id and
                scene.catch_species and scene.catch_weight_g is not None):
            return replace(item,phase=RodPhase.CATCH,cast=False,hooked=False,
                           species=scene.catch_species,weight_g=scene.catch_weight_g,grade=scene.catch_grade)
        return item

    def scene(self):
        with self._lock:
            return self._scene if self.healthy() else None

    def process_id(self):
        with self._lock:
            return self._generation[0] if isinstance(self._generation,tuple) else None

    def session_key(self):
        with self._lock:return self._generation

    def healthy(self):
        with self._lock:
            return (not self.error and self._observed_at is not None
                    and 0 <= self._clock()-self._observed_at <= 2)

    def snapshot(self, max_age=2.):
        with self._lock:
            if self.error:
                return ()
            now = self._clock()
            return tuple(x for x in self._items.values() if 0 <= now-x.updated <= max_age)

    def bind_active(self, key):
        with self._lock:
            active = [x for x in self.snapshot() if x.active]
            if len(active) != 1:
                return None
            item = active[0]
            if any(x.slot_key == key and x.identity != item.identity for x in self._items.values()):
                raise ValueError('Одна клавиша привязана к двум снастям')
            if item.slot_key not in (None, key):
                raise ValueError('Две клавиши выбрали одну снасть')
            self._items[item.identity] = replace(item, slot_key=key)
            self._known[item.identity] = self._items[item.identity]
            self._save_bindings()
            return item.identity

    def _save_bindings(self):
        if self._cache_path is None or not isinstance(self._generation,tuple):return
        try:
            rows=[dict(identity=x.identity,kind=x.kind,key=x.slot_key) for x in self._known.values() if x.slot_key]
            temporary=self._cache_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(generation=self._generation,rods=rows)),encoding='utf-8')
            temporary.replace(self._cache_path)
        except OSError:pass

    def observe_screen(self, key, *, fish, catch, distance):
        with self._lock:
            matches = [x for x in self.snapshot() if x.slot_key == key and x.active]
            if len(matches) != 1:
                return RodPhase.UNKNOWN
            item = matches[0]
            phase = classify_screen(fish=fish or item.hooked, catch=catch,
                                    distance=distance, on_rest=item.on_rest)
            cast = (False if phase in (RodPhase.READY, RodPhase.CATCH) else
                    True if phase in (RodPhase.REEL_IN, RodPhase.DEPLOYED, RodPhase.HOOKED) else item.cast)
            self._items[item.identity] = replace(item, phase=phase, cast=cast)
            self._known[item.identity] = self._items[item.identity]
            return phase

    def mark_casting(self, key):
        with self._lock:
            for identity, item in self._items.items():
                if item.slot_key == key:
                    self._items[identity] = replace(item, phase=RodPhase.CASTING, cast=None)
                    self._known[identity] = self._items[identity]

    def mark_cast_complete(self, key):
        # Completion of an input sequence alone does not prove a cast landed.
        with self._lock:
            for identity, item in self._items.items():
                if item.slot_key == key:
                    self._items[identity] = replace(item, phase=RodPhase.UNKNOWN, cast=None)
                    self._known[identity] = self._items[identity]

    def fish_priority(self):
        return next((x for x in self.snapshot() if x.hooked and x.slot_key), None)
