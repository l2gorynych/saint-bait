"""Memory-driven fishing session. Feeder and spinning strategies share actions."""
import random
import time
import json
from datetime import datetime
from .paths import data_path
from . import state
from .auto_rods import AutoRodController
from .controls import SessionCancelled,human_sleep,release_all
from .logging_utils import log
from .game_input import GameInput
from .rods import RodPhase
from .strategies.feeder import FeederStrategy
from .strategies.spinning import SpinningStrategy
from .fight_control import FightControl
from .aim_control import CastAim
from .catch_policy import release_small
from .automatic_drag import BrakeCalibration
from .keepnet import keepnet_full


def number(widget,default,low,high):
    try:value=float(widget.get().strip() or default)
    except (ValueError,TypeError):raise ValueError('Введите число в настройках ловли')
    if not low<=value<=high:raise ValueError(f'Значение должно быть от {low} до {high}')
    return value


def resolve_mode(requested,rods):
    kinds={rod.kind for rod in rods}
    if not rods:raise ValueError('Снасти ещё не определены')
    if requested=='auto':
        held=next((rod.kind for rod in rods if rod.active),None)
        requested=held or ('feeder' if kinds=={'feeder'} else 'spinning' if kinds=={'spinning'} else '')
    if requested not in ('feeder','spinning'):
        raise ValueError('Выберите фидер или возьмите спиннинг в руки')
    chosen=tuple(rod for rod in rods if rod.kind==requested)
    if requested=='feeder' and not 1<=len(chosen)<=3:raise ValueError('Для фидера нужны 1–3 донные снасти')
    if requested=='spinning' and len(chosen)!=1:raise ValueError('Для спиннинга возьмите одну снасть в руки')
    return requested,chosen


class MemorySession:
    def __init__(self,ui):
        self.ui=ui
        self.registry=ui.rod_registry
        scene=self.registry.scene()
        if scene is None:raise SessionCancelled('Нет свежих данных игры')
        net_field=getattr(ui,'entry_net_key',None)
        net_key=net_field.get().strip().lower() if net_field is not None else ''
        self.input=GameInput(ui,scene.bindings,overrides={'net':net_key} if net_key else None)
        self.target_clip=int(number(ui.entry_clip,8,1,300))
        self.fight=FightControl()
        self.aim=CastAim(getattr(ui,'cast_start_scene',None) or scene)
        self.mode,rods=resolve_mode(ui.fishing_mode,self.registry.snapshot())
        self.controller=AutoRodController(ui)
        ui.auto_rod_controller=self.controller
        self.strategy=(FeederStrategy() if self.mode=='feeder' else SpinningStrategy(
            bool(ui.check_jig_mode.get()),number(ui.entry_jig_reel_time,1.42,.1,30),
            number(ui.entry_jig_pause_time,2.58,.1,30)))
        self.cast_s=(min(8.,max(.5,self.target_clip*.11)) if self.mode=='feeder' else
                     number(ui.entry_spinning_cast,1.,.1,8.))
        requested_limit=number(ui.entry_stop_time,120,0,10080)*60
        self.limit_s=min(requested_limit or 7200,7200)
        self.started=time.monotonic()
        self.caught=0
        slots=[value.strip() for value in ui.entry_feeder_slots.get().split(',') if value.strip()]
        if self.mode=='feeder':
            if len(slots)<len(rods) or len(set(slots))!=len(slots) or any(value not in tuple(str(n) for n in range(1,8)) for value in slots):
                raise ValueError('Укажите разные слоты фидеров от 1 до 7 через запятую')
            self.keys=[self.input.token('slot'+value) for value in slots[:len(rods)]]
        else:
            # A held spinning rod needs no guessed quick-slot assignment.
            self.keys=['']
        self._net_attempted=None
        self._last_phase=None
        self._last_progress=None
        self._progress_identity=None
        self.auxiliary=None
        for enabled,widget in ((ui.check_do_gb,ui.entry_gb_key),):
            if enabled.get() and widget.get() not in tuple(str(n) for n in range(1,8)):
                raise ValueError('Для еды и прикормки укажите номер слота от 1 до 7')

    def scene(self):
        scene=self.registry.scene()
        if scene is None:raise SessionCancelled('Потеряны данные игры; управление остановлено')
        if scene.dialogs and not scene.catch_id:
            # Stop input while the game builds a dialog, but allow its result
            # model to become available before declaring an unrelated window.
            self.input.release()
            deadline=time.monotonic()+.8
            while scene.dialogs and not scene.catch_id and time.monotonic()<deadline:
                human_sleep(.05)
                scene=self.registry.scene()
                if scene is None:raise SessionCancelled('Потеряны данные игры')
        if dict(scene.bindings)!=self.input.bindings:
            raise SessionCancelled('Клавиши в игре изменились. Нажмите Старт для применения.')
        if scene.dialogs and not scene.catch_id:
            raise SessionCancelled('В игре открыто другое окно; управление остановлено')
        return scene

    def wait(self,predicate,timeout,message):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if state.stop_event.is_set():raise SessionCancelled('Рыбалка остановлена')
            self.scene()
            value=predicate()
            if value:return value
            human_sleep(.08)
        raise SessionCancelled(message)

    def active(self):
        return self.controller.active(max_age=.3)

    def prepare(self):
        if keepnet_full(self.scene()):
            raise SessionCancelled('Садок заполнен. Освободите место перед началом ловли.')
        state.is_spinning_mode=self.mode=='spinning'
        state.is_casting=False
        self.controller.start()
        if self.mode=='feeder':
            if any(rod.active and rod.kind!='feeder' for rod in self.registry.snapshot()):
                raise SessionCancelled('Уберите другую снасть из рук перед запуском фидера')
            self.controller.prepare(None,None,self.keys,on_ready=self.cast_ready)
        else:
            rod=self.controller.wait_active()
            if rod.kind!='spinning':raise SessionCancelled('Выбранный слот не содержит спиннинг')
            self.registry.bind_active(self.keys[0])
        log('Ловля: '+('фидер' if self.mode=='feeder' else 'спиннинг')+' · данные игры',self.ui)

    def select(self,rod):
        rod=next((current for current in self.registry.snapshot() if current.identity==rod.identity),None)
        if rod is None:raise SessionCancelled('Снасть сейчас не наблюдается в игре')
        if not rod.active:
            if self.mode=='spinning':raise SessionCancelled('Возьмите спиннинг в руки для продолжения')
            self.input.release()
            if rod.slot_key is None:self.controller.locate(rod.identity,self.keys)
            else:self.controller.select(rod.slot_key,urgent=rod.hooked)
        active=self.active()
        if active is None or (active.identity!=rod.identity and not active.hooked):raise SessionCancelled('Выбор снасти не подтверждён')
        return active

    def cast(self,rod):
        self.input.release()
        self.check_cast_limits()
        if not self.apply_rod_settings(rod):return
        self.restore_cast_view(rod)
        self.controller.before_cast(None,None,rod.slot_key)
        # A pending result, deployed line or missing data never authorizes a cast.
        if self.scene().catch_id:raise SessionCancelled('Окно улова ещё не закрыто')
        self.check_cast_limits()
        state.is_casting=True
        try:
            self.input.hold('reel',True)
            human_sleep(min(8.,max(.1,self.cast_s*random.uniform(.97,1.03))))
        finally:
            self.input.hold('reel',False)
        human_sleep(random.uniform(1.8,2.6))
        self.controller.after_cast(None,None,rod.slot_key)
        active=self.active()
        if active and not active.hooked:
            # A short requested winding closes the bail without toggling a
            # possibly already closed spool. Load protection remains enabled.
            self.input.hold('reel',True)
            human_sleep(.15)
            self.input.hold('reel',False)
        state.is_casting=False
        self._net_attempted=None
        self._last_progress=(time.monotonic(),None)
        if self.mode=='feeder':self.controller.rest()
        if hasattr(self.strategy,'cast_finished'):self.strategy.cast_finished(rod.identity)

    def check_cast_limits(self):
        scene=self.scene()
        if keepnet_full(scene):raise SessionCancelled('Садок заполнен · заброс отменён')
        if scene.keepnet_count is None or scene.keepnet_capacity is None:
            raise SessionCancelled('Не удалось проверить место в садке · заброс отменён')
        if time.monotonic()-self.started>=self.limit_s:
            raise SessionCancelled('Время сессии истекло · заброс отменён')

    def apply_rod_settings(self,rod):
        for _ in range(301):
            current=self.active()
            if current is None or current.identity!=rod.identity or current.hooked or current.phase!=RodPhase.READY:
                raise SessionCancelled('Настройка снасти разрешена только перед забросом')
            if current.clip_m is None:raise SessionCancelled('Нет значения клипсы из игры')
            if current.clip_m==self.target_clip:break
            old=current.clip_m
            self.input.adjust_clip(1 if old<self.target_clip else -1)
            changed=self.wait(lambda:self.active() if self.active() and self.active().identity==rod.identity
                              and self.active().clip_m!=old else None,2,'Изменение клипсы не подтверждено')
            if changed.hooked or changed.clip_m is None or abs(changed.clip_m-self.target_clip)>=abs(old-self.target_clip):
                raise SessionCancelled('Клипса изменилась неожиданно; заброс отменён')
        else:raise SessionCancelled('Не удалось выставить клипсу')
        calibration=BrakeCalibration(rod.identity)
        for _ in range(60):
            current=self.active()
            if current is None or current.identity!=rod.identity or current.phase!=RodPhase.READY:
                raise SessionCancelled('Снасть изменилась при настройке фрикциона')
            if any(x.hooked for x in self.registry.snapshot()):return False
            try:direction=calibration.observe(current)
            except ValueError as error:raise SessionCancelled(str(error)) from error
            if direction==0:
                self.fight.set_brake_profile(rod.identity,calibration.profile())
                log('Автофрикцион: '+str(current.drag_setting)+' · запас по прочности снасти',self.ui)
                return True
            old=current.drag_setting
            self.input.adjust_drag(direction)
            changed=self.wait(lambda:self.active() if self.active() and self.active().identity==rod.identity
                              and self.active().drag_setting!=old else None,2,'Фрикцион не изменился')
            if changed.drag_setting!=old+direction:raise SessionCancelled('Фрикцион изменился неожиданно')
        raise SessionCancelled('Не удалось подобрать фрикцион')

    def cast_ready(self,rod):
        if self.scene().net_present:
            self.input.release()
            self.input.press('net')
            self.wait(lambda:not self.scene().net_present,3,'Подсак не убран перед перезабросом')
            self._net_attempted=None
        if self.auxiliary is not None:self.auxiliary.before_cast()
        rod=self.select(rod)
        if rod.phase==RodPhase.READY:self.cast(rod)

    def restore_cast_view(self,rod):
        self.input.release()
        # Releasing RMB lowers the rod. Camera motion is allowed only after
        # the actual rig is ready; no aiming while a fish is on the line.
        human_sleep(.3)
        for _ in range(16):
            active=self.active()
            if active is None or active.identity!=rod.identity or active.phase!=RodPhase.READY or active.hooked:
                raise SessionCancelled('Снасть не готова к возврату направления заброса')
            before=self.scene()
            move=self.aim.correction(before)
            if move==(0,0):return
            self.input.move_view(*move)
            human_sleep(.18)
            self.aim.observe(before,self.scene(),move)
        raise SessionCancelled('Не удалось вернуть направление; заброс отменён')

    def retrieve(self,rod):
        if rod.line_m is None:raise SessionCancelled('Нет данных лески')
        scene=self.scene()
        if scene.net_present and (not rod.hooked or
                (rod.fish_distance is not None and rod.fish_distance>3.6)):
            self.input.release()
            self.input.press('net')
            self.wait(lambda:not self.scene().net_present,3,'Подсак не убран для дальнейшей подмотки')
            self._net_attempted=None
            return
        decision=self.fight.decide(rod,net=scene.net_present)
        if decision.drag:
            self.input.adjust_drag(decision.drag)
            self.fight.sent(rod,decision.drag)
            log('Фрикцион '+str(rod.drag_setting)+(' → ')+str(rod.drag_setting+decision.drag)+
                ' · '+decision.reason,self.ui)
            return
        if decision.waiting:
            self.input.release()
            return
        if self.controller.overload():
            self.input.release()
            return
        if scene.net_present:
            # With the net equipped LMB operates the net, not the reel.
            # Keep winding released and lift the rod into the net. The same
            # fast load guard releases RMB when tension reaches its ceiling.
            self.input.hold('reel',False)
            self.input.hold('pull',True)
            return
        within_net=(rod.fish_distance is not None and rod.fish_distance<=3.0)
        if rod.hooked and within_net and not scene.net_present and self._net_attempted!=rod.identity:
            self.input.hold('reel',False)
            self.input.hold('pull',True)
            self.input.press('net')
            self.wait(lambda:self.scene().net_present or self.scene().catch_id or
                      (self.active() and self.active().phase==RodPhase.CATCH),
                      3,'Подсак не появился после нажатия '+self.input.token('net'))
            self._net_attempted=rod.identity
            log('Подсак подтверждён игрой',self.ui)
            return
        winding=True if self.mode=='feeder' else self.strategy.reeling(rod)
        self.input.hold('reel',winding)
        self.input.hold('pull',decision.lift)
        if self._progress_identity!=rod.identity:
            self._last_progress=None
            self._progress_identity=rod.identity
        if self._last_progress is None or self._last_progress[1] is None or abs(rod.line_m-self._last_progress[1])>.15:
            self._last_progress=(time.monotonic(),rod.line_m)
        elif time.monotonic()-self._last_progress[0]>120:
            raise SessionCancelled('Леска долго не меняется; проверьте снасть')

    def confirm(self,rod):
        self.input.release()
        scene=self.wait(lambda:self.scene() if self.scene().catch_id and self.scene().catch_ready else None,
                        15,'Окно улова не готово к подтверждению')
        result_id=scene.catch_id
        human_sleep(random.uniform(.45,.85))
        scene=self.scene()
        if scene.catch_id!=result_id or not scene.catch_ready:raise SessionCancelled('Окно улова изменилось')
        from .vision import catch_awards
        trophy,card=catch_awards(self.registry.process_id())
        if rod.grade in (3,4):trophy=True
        release=release_small(rod.grade,trophy,card)
        if not release and keepnet_full(scene):
            raise SessionCancelled('Садок заполнен. Рыба оставлена в окне улова — освободите место или решите вручную.')
        key=scene.release_key if release else scene.keep_key
        self.input.press_token(key)
        self.wait(lambda:not self.scene().catch_id,7,'Игра не подтвердила закрытие окна улова')
        self.ui.update_stats(fish_inc=1,is_trophy=trophy,is_card=card,rod_idx=self.keys.index(rod.slot_key))
        self.caught+=1
        receipt=dict(time=datetime.now().astimezone().isoformat(),species=rod.species,weight_g=rod.weight_g,
                     trophy=trophy,card=card,slot=rod.slot_key,released=release,grade=rod.grade)
        try:
            with open(data_path('catches.jsonl'),'a',encoding='utf-8') as stream:
                stream.write(json.dumps(receipt,ensure_ascii=False)+'\n')
        except OSError:pass
        log('Улов подтверждён'+(' · снасть '+rod.slot_key if rod.slot_key else ' · спиннинг'),self.ui)
        if trophy:log('ТРОФЕЙ · '+str(rod.species or 'рыба')+' · '+str(rod.weight_g or '?')+' г',self.ui)
        if card:log('Получена карточка',self.ui)
        if release:log('Рыба отпущена'+(' · незачётная' if rod.grade==1 else ''),self.ui)
        if self.ui.check_catch_alerts.get():
            from .notifications import send_bot_msg
            send_bot_msg(self.ui,'Улов подтверждён · снасть '+rod.slot_key,is_danger=trophy or card)
        self._net_attempted=None
        self._last_progress=None
        self.fight.reset(rod.identity)
        # Read state after closure, never infer readiness from the key press.
        self.wait(lambda:self.active() if self.active() and self.active().phase!=RodPhase.CATCH else None,
                  7,'Состояние снасти после улова не обновилось')
        if self.scene().net_present:
            self.input.press('net')
            self.wait(lambda:not self.scene().net_present,7,'Подсак не убран; следующий заброс отменён')

    def run(self):
        from .auxiliary import AuxiliaryActions
        self.auxiliary=AuxiliaryActions(self)
        self.prepare()
        while not state.stop_event.is_set():
            scene=self.scene()
            if time.monotonic()-self.started>=self.limit_s:
                self.input.release()
                log('Время сессии истекло · ловля завершена',self.ui)
                return
            rods=tuple(rod for rod in self.registry.snapshot() if rod.kind==self.mode)
            if keepnet_full(scene):
                self.input.release()
                log(f'Садок заполнен {scene.keepnet_count}/{scene.keepnet_capacity} · ловля завершена',self.ui)
                return
            chosen=self.strategy.choose(rods)
            if chosen is None:
                self.input.release()
                self.auxiliary.idle()
                human_sleep(.12)
                continue
            rod=self.select(chosen)
            if rod.phase==RodPhase.CATCH:
                self.confirm(rod)
            elif rod.phase==RodPhase.READY:
                self.cast_ready(rod)
            elif rod.phase in (RodPhase.HOOKED,RodPhase.REEL_IN):
                self.retrieve(rod)
            elif rod.phase in (RodPhase.CASTING,RodPhase.DEPLOYED):
                self.input.release()
            else:
                raise SessionCancelled('Состояние снасти не определено')
            human_sleep(.08)


def core_loop(ui):
    session=MemorySession(ui)
    try:
        session.run()
    finally:
        state.is_casting=False
        session.controller.stop()
        session.input.release()
