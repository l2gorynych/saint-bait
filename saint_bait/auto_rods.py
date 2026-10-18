"""Automatic feeder setup and decisions; original retrieval remains in engine.py."""
import time
import threading
from . import state
from .controls import human_press, human_sleep, safe_mouse, put_rod_on_stand, SessionCancelled
from .logging_utils import log
from .rods import RodPhase
from .pacing import ActionPacing


class AutoRodController:
    def __init__(self, ui):
        self.ui = ui
        self.registry = ui.rod_registry
        self._relieving_load = False
        self._load_identity = None
        self._load_lock = threading.RLock()
        self.pacing = ActionPacing()
        self.input_guard = None

    def start(self):
        from .load_control import LoadInputGuard
        from .controls import input_down,input_up
        self.input_guard = LoadInputGuard(self,
            (self.ui.entry_reel_btn.get(),self.ui.entry_pull_btn.get()),
            input_down,input_up)
        self.input_guard.start()

    def stop(self):
        if self.input_guard:
            self.input_guard.stop()

    def pause(self, action, urgent=False):
        delay = self.pacing.delay(action,urgent)
        if delay:
            human_sleep(delay)

    def wait_active(self, key=None, timeout=7):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if state.stop_event.is_set():
                raise SessionCancelled('Рыбалка остановлена')
            if not self.registry.healthy():
                state.stop_event.set()
                raise SessionCancelled('Потеряны данные игры; управление остановлено')
            active = [x for x in self.registry.snapshot() if x.active]
            if len(active)==1 and not active[0].on_rest and (key is None or active[0].slot_key==key):
                return active[0]
            state.stop_event.wait(.1)
        state.stop_event.set()
        raise SessionCancelled('Снасть в руках не подтверждена. Проверьте клавиши слотов.')

    def select(self, key, urgent=False):
        items = self.registry.snapshot()
        if not self.registry.healthy() or not any(x.slot_key==key for x in items):
            state.stop_event.set()
            raise SessionCancelled('Снасть '+key+' сейчас недоступна; действие отменено')
        active = [x for x in items if x.active and x.slot_key==key]
        if not active:
            self.pause('select',urgent)
            human_press(key,self.ui)
            self.wait_active(key)
            self.pause('pickup')
        return self.wait_active(key)

    def observe(self, sct, win, key, raw=None):
        current = [x for x in self.registry.snapshot() if x.active and x.slot_key==key and x.memory_metrics]
        return current[0].phase if len(current)==1 else RodPhase.UNKNOWN

    def prepare(self, sct, win, keys, on_ready=None):
        items = tuple(x for x in self.registry.snapshot() if x.kind=='feeder')
        if not 1<=len(items)<=3:
            raise RuntimeError('Авторежим сейчас рассчитан на 1–3 донные снасти. Для других снастей выключите автоопределение.')
        if len(keys)!=len(items) or len(set(keys))!=len(keys):
            raise RuntimeError('Укажите отдельную клавишу для каждой обнаруженной снасти.')
        if all(not x.active and x.phase==RodPhase.DEPLOYED for x in items):
            log('Все снасти заброшены · ожидаю рыбу',self.ui)
            return []
        if all(x.slot_key in keys for x in items):
            for rod in items:
                if rod.phase==RodPhase.READY:
                    selected=self.select(rod.slot_key)
                    if on_ready is not None:on_ready(selected)
                    else:self.rest()
                    if any(x.hooked for x in self.registry.snapshot()):return []
            return [x.slot_key for x in self.registry.snapshot() if x.phase==RodPhase.READY]
        if any(x.active for x in items):
            self.rest()
        for key in keys:
            human_press(key,self.ui)
            selected=self.wait_active()
            if selected.kind!='feeder':
                raise RuntimeError('Слот '+key+' содержит другую снасть. Укажите слоты фидеров в настройках.')
            # The inventory may still expose the previous active rod for a frame.
            self.pause('pickup')
            identity = self.registry.bind_active(key)
            if identity is None:
                raise RuntimeError('Не удалось сопоставить снасть с клавишей '+key)
            phase = self.observe(sct,win,key)
            if phase==RodPhase.UNKNOWN:
                raise RuntimeError('Снасть '+key+': состояние в памяти не подтверждено. Заброс отменён.')
            log('Снасть '+key+': '+('рыба на крючке' if phase==RodPhase.HOOKED else
                                  'можно забрасывать' if phase==RodPhase.READY else 'уже заброшена'),self.ui)
            if phase==RodPhase.READY and on_ready is not None:
                # The session casts this verified rig immediately and returns
                # it to its rest. Starting with empty hands is normal.
                on_ready(self.wait_active(key))
                if any(x.hooked for x in self.registry.snapshot()):return []
            else:
                self.rest()
        return [x.slot_key for x in self.registry.snapshot() if x.phase==RodPhase.READY]

    def locate(self,identity,keys):
        # An unbound deployed rod is left alone until it actually needs input.
        # Discover its key then, and persist only mappings verified in hand.
        for key in keys:
            known=next((x for x in self.registry.snapshot() if x.slot_key==key),None)
            if known:
                if known.identity==identity:return self.select(key,urgent=True)
                continue
            human_press(key,self.ui)
            selected=self.wait_active()
            self.pause('pickup')
            self.registry.bind_active(key)
            selected=self.wait_active(key)
            if selected.identity==identity or selected.hooked:return selected
            self.rest()
        raise SessionCancelled('Не удалось определить слот нужной снасти')

    def rest(self):
        active = [x for x in self.registry.snapshot() if x.active]
        if len(active)!=1:
            raise RuntimeError('Снасть для установки на подставку не определена')
        identity = active[0].identity
        put_rod_on_stand(self.ui)
        deadline = time.monotonic()+7
        retry_at=time.monotonic()+2.
        retried=False
        while time.monotonic()<deadline:
            items = self.registry.snapshot()
            if any(x.identity==identity and x.on_rest and not x.active for x in items):
                return
            current=next((x for x in items if x.identity==identity),None)
            if not retried and time.monotonic()>=retry_at and current and current.active and not current.on_rest:
                # The first press can be ignored during the pickup animation.
                # Never toggle again once a rest transition has begun.
                put_rod_on_stand(self.ui)
                retried=True
            human_sleep(.1)
        raise RuntimeError('Установка снасти на подставку не подтверждена')

    def distance(self):
        active = [x for x in self.registry.snapshot() if x.active and x.memory_metrics]
        if len(active)!=1:
            return 999
        rod = active[0]
        return 0 if rod.phase==RodPhase.READY else rod.line_m if rod.line_m is not None else 999

    def active(self, max_age=2.):
        active = [x for x in self.registry.snapshot(max_age=max_age) if x.active and x.memory_metrics]
        return active[0] if len(active)==1 else None

    def fish_attached(self):
        rod = self.active()
        return rod is not None and rod.hooked

    def overload(self):
        from .load_control import load_limits
        with self._load_lock:
            rod = self.active(max_age=.3)
            if rod is None or rod.phase in (RodPhase.READY,RodPhase.CATCH,RodPhase.CASTING):
                self._relieving_load = False
                self._load_identity = None
                return False
            if self._load_identity!=rod.identity:
                self._relieving_load = False
                self._load_identity = rod.identity
            try:
                release_at,resume_below = load_limits(rod)
            except ValueError as error:
                state.stop_event.set()
                raise SessionCancelled(str(error)+'; вываживание остановлено') from error
            self._relieving_load = rod.load_force >= (resume_below if self._relieving_load else release_at)
            return self._relieving_load

    def priority(self, keys):
        rod = self.registry.fish_priority()
        if rod is None:
            return False
        hooked = [x for x in self.registry.snapshot() if x.hooked]
        urgent = len(hooked)>1 or (rod.load_fraction is not None and rod.load_fraction>=.7)
        self.pause('bite',urgent)
        current = next((x for x in self.registry.snapshot() if x.identity==rod.identity and x.hooked),None)
        if current is None:
            return False
        self.select(rod.slot_key,urgent=True)
        current = self.wait_active(rod.slot_key)
        if not current.hooked:
            return False
        state.cur_idx = keys.index(rod.slot_key)
        state.cur_rod_in_hand = rod.slot_key
        state.t_pull = time.time()
        state.pending_bite = False
        state.state = 1
        log('Снасть '+rod.slot_key+': подтверждена рыба, начинаю вываживание',self.ui)
        return True

    def before_cast(self, sct, win, key):
        self.select(str(key))
        deadline = time.monotonic()+45
        ready_frames = 0
        while time.monotonic()<deadline:
            phase = self.observe(sct,win,str(key))
            if phase==RodPhase.READY:
                ready_frames += 1
                if ready_frames<2:
                    human_sleep(.2)
                    continue
                safe_mouse('up',self.ui.entry_reel_btn.get(),self.ui)
                self.pause('before_cast')
                self.registry.mark_casting(str(key))
                return True
            ready_frames = 0
            if phase==RodPhase.HOOKED:
                state.state = 1
                state.t_pull = time.time()
                log('Заброс отменён: на снасти '+str(key)+' рыба',self.ui)
                state.stop_event.set()
                raise SessionCancelled('На снасти рыба; повторный заброс отменён')
            if phase!=RodPhase.REEL_IN:
                state.stop_event.set()
                raise SessionCancelled('Снасть '+str(key)+': готовность к забросу не подтверждена')
            log('Снасть '+str(key)+': докручиваю леску перед забросом',self.ui)
            if self.overload():
                safe_mouse('up',self.ui.entry_reel_btn.get(),self.ui)
                human_sleep(.1)
                continue
            safe_mouse('down',self.ui.entry_reel_btn.get(),self.ui)
            human_sleep(.5)
            safe_mouse('up',self.ui.entry_reel_btn.get(),self.ui)
        state.stop_event.set()
        raise SessionCancelled('Докрутка заняла слишком много времени; снасть '+str(key)+' требует проверки')

    def after_cast(self, sct, win, key):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            phase = self.observe(sct,win,str(key))
            if phase in (RodPhase.REEL_IN,RodPhase.HOOKED):
                return
            human_sleep(.3)
        state.stop_event.set()
        raise SessionCancelled('Снасть '+str(key)+': результат заброса не подтверждён. Требуется проверка.')
