"""Optional food, groundbait and lighting; never interrupt an attached fish."""
import time
import random
from . import state
from .controls import human_sleep
from .logging_utils import log
from .food_control import FoodControl


class AuxiliaryActions:
    def __init__(self,session):
        self.session=session
        self.ui=session.ui
        self.last_food,self.last_bait=time.monotonic(),time.monotonic()
        self.last_light=0.
        self.light_enabled=False
        self.food=FoodControl()
        self.food_slot=self.ui.entry_food_slot.get().strip()
        if self.food_slot not in tuple(str(n) for n in range(1,8)):
            raise ValueError('Укажите слот еды от 1 до 7')

    def idle(self):
        rods=self.session.registry.snapshot()
        if any(rod.hooked for rod in rods):return
        now=time.monotonic()
        if self.ui.check_do_cons.get() and self.food.needs_food(self.session.scene().satiety,now):
            self.eat()
        if (self.session.mode=='feeder' and self.ui.check_do_gb.get()
                and now-self.last_bait>=float(self.ui.entry_gb_game_hours.get() or 12)*150):
            self.groundbait()
            self.last_bait=now

    def eat(self):
        session=self.session
        if any(rod.hooked for rod in session.registry.snapshot()):return
        scene=session.scene()
        before=scene.satiety
        if before is None:return
        session.input.release()
        held=session.active()
        if held is not None and session.mode=='feeder':return
        session.input.press('slot'+self.food_slot)
        deadline=time.monotonic()+10.
        peak=before
        stable_since=time.monotonic()
        while time.monotonic()<deadline:
            if any(rod.hooked for rod in session.registry.snapshot()):return
            after=session.scene().satiety
            if after is not None and after>peak+.002:
                peak=after
                stable_since=time.monotonic()
            if peak-before>=.01 and time.monotonic()-stable_since>=1.2:
                gain=self.food.measured(before,peak,time.monotonic())
                remaining=self.food.portions_needed(peak)
                log(f'Еда: сытость {peak:.0%} · +{gain:.0%} · осталось ≈{remaining} порций',self.ui)
                return
            human_sleep(.15)
        gain=self.food.measured(before,peak,time.monotonic())
        log(f'Еда: сытость {peak:.0%} · +{gain:.0%}' if gain is not None else
            'Еда не восстановила сытость · проверьте выбранную еду в игре',self.ui)

    def groundbait(self):
        session=self.session
        session.input.release()
        session.controller.stop()
        session.controller.input_guard=None
        try:
            action='slot'+self.ui.entry_gb_key.get()
            for _ in range(3):
                session.input.press(action)
                human_sleep(.5)
            human_sleep(1.)
            duration=min(8.,max(.1,float(self.ui.entry_gb_dur.get() or 8)*.11))
            for _ in range(10):
                if any(rod.hooked for rod in session.registry.snapshot()):break
                session.scene()
                session.input.hold('reel',True)
                human_sleep(duration*random.uniform(.97,1.03))
                session.input.hold('reel',False)
                human_sleep(random.uniform(1.6,2.2))
            session.input.press(action)
            log('Прикормка завершена',self.ui)
        finally:
            session.input.release()
            if not state.stop_event.is_set():session.controller.start()

    def before_cast(self):
        # Food is handled only by the idle loop, after ready rods are cast.
        if not self.ui.check_auto_flashlight.get() and not self.ui.check_stop_at_night.get():return
        if time.monotonic()-self.last_light<20:return
        self.last_light=time.monotonic()
        # Retain optional legacy lighting/night behaviour; screen brightness is
        # separate from the memory-only fish, line and load decisions.
        from .vision import game_brightness
        brightness=game_brightness(self.session.registry.process_id())
        if brightness is None:return
        if self.ui.check_auto_flashlight.get() and brightness<40 and not self.light_enabled:
            self.session.input.press('flashlight')
            self.light_enabled=True
        if self.ui.check_stop_at_night.get() and self.session.mode=='spinning':
            while brightness<40:
                self.session.scene()
                human_sleep(5.)
                brightness=game_brightness(self.session.registry.process_id())
                if brightness is None:return
