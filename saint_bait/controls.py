"""Focused game input and mouse/keyboard helpers. Original timings retained."""

from . import state
from .logging_utils import log
from .settings import game_title
import keyboard
import pyautogui
import pydirectinput
import pygetwindow as gw
import random
import time
import winsound
import threading
import ctypes as C
from ctypes import wintypes as W
from .bindings import direct_key

# PyDirectInput omits numeric-pad names, although its scan-code path supports
# their non-extended hardware codes. Keep them distinct from arrow keys.
pydirectinput.KEYBOARD_MAPPING.update(dict(zip(
    ('num0','num1','num2','num3','num4','num5','num6','num7','num8','num9'),
    (0x52,0x4F,0x50,0x51,0x4B,0x4C,0x4D,0x47,0x48,0x49))))


def is_game_focused(window,ui_ref=None):
    if window is None or window.title.strip()!=game_title:
        return False
    registry=getattr(ui_ref,'rod_registry',None) if ui_ref is not None else None
    pid=registry.process_id() if registry is not None else None
    if pid is None:return ui_ref is None
    hwnd=getattr(window,'_hWnd',None)
    if not hwnd:return False
    api=C.WinDLL('user32',use_last_error=True)
    api.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    actual=W.DWORD()
    api.GetWindowThreadProcessId(hwnd,C.byref(actual))
    return actual.value==pid


class SessionCancelled(RuntimeError):
    """Stop requested during a bounded input or delay."""


class FocusGuard:
    """Release held input promptly if an active session loses its game window."""
    def __init__(self, ui):
        self.ui = ui
        self._done = threading.Event()
        self._seen_game = False
        self._worker = None

    def start(self):
        self._worker = threading.Thread(target=self._run,name='SaintBait-FocusGuard',daemon=True)
        self._worker.start()

    def stop(self):
        self._done.set()
        if self._worker:
            self._worker.join(timeout=.3)

    def check_once(self):
        active = gw.getActiveWindow()
        focused = is_game_focused(active,self.ui)
        if focused:
            self._seen_game = True
        elif self._seen_game:
            state.stop_event.set()
            release_all(self.ui)
            log('Игра потеряла фокус. Управление остановлено; нажмите Старт для продолжения.',self.ui)
            self._done.set()

    def _run(self):
        while not self._done.wait(.05) and not state.stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                state.stop_event.set()
                self._done.set()


def check_running():
    if state.stop_event.is_set():
        raise SessionCancelled('Рыбалка остановлена')


def wait_for_focus(ui_ref=None, timeout=30):
    for _ in range(timeout):
        if state.stop_event.is_set():
            return False
        active_win = gw.getActiveWindow()
        if is_game_focused(active_win,ui_ref):
            time.sleep(random.uniform(0.03, 0.08))
            return True
        state.stop_event.wait(0.5)
    log('Критична помилка: Фокус втрачено.', ui_ref)
    return False


def bezier_mouse_move(x2, y2, duration=0.2):
    x1, y1 = pydirectinput.position()
    cp1_x, cp1_y = (x1 + random.randint(-20, 20), y1 + random.randint(-20, 20))
    cp2_x, cp2_y = (x2 + random.randint(-20, 20), y2 + random.randint(-20, 20))
    steps = random.randint(15, 25)
    for i in range(steps + 1):
        t = i / steps
        curr_x = (1 - t) ** 3 * x1 + 3 * (1 - t) ** 2 * t * \
                  cp1_x + 3 * (1 - t) * t ** 2 * cp2_x + t ** 3 * x2
        curr_y = (1 - t) ** 3 * y1 + 3 * (1 - t) ** 2 * t * \
                  cp1_y + 3 * (1 - t) * t ** 2 * cp2_y + t ** 3 * y2
        pydirectinput.moveTo(int(curr_x), int(curr_y))
        time.sleep(duration / steps)


def jitter(v, p=0.03):
    return v * (1 + random.uniform(-p, p))


def human_sleep(s):
    if state.stop_event.wait(max(0.01, jitter(s))):
        raise SessionCancelled('Рыбалка остановлена')


def human_press(k, ui_ref=None):
    if str(k).startswith('mouse:'):
        safe_mouse('click',str(k).split(':',1)[1],ui_ref)
        return
    k=direct_key(k)
    if k not in pydirectinput.KEYBOARD_MAPPING:
        raise SessionCancelled('Клавиша не поддерживается вводом: '+str(k))
    down = False
    try:
        if not wait_for_focus(ui_ref, 30):
            log('Критична помилка: Фокус втрачено. Екстрене завершення.', ui_ref)
            state.stop_event.set()
            if ui_ref is not None:
                ui_ref.stop_logic()
            raise SessionCancelled('Не удалось дождаться фокуса игры')
        check_running()
        hold = abs(random.gauss(0.12, 0.04))
        hold = max(0.05, min(hold, 0.3))
        pydirectinput.keyDown(k)
        down = True
        if state.stop_event.wait(hold):
            raise SessionCancelled('Рыбалка остановлена')
        pydirectinput.keyUp(k)
        down = False
        if k in ['1', '2', '3']:
            state.cur_rod_in_hand = k
        after_delay = abs(random.gauss(0.2, 0.07))
        if state.stop_event.wait(max(0.1, min(after_delay, 0.5))):
            raise SessionCancelled('Рыбалка остановлена')
    except SessionCancelled:
        raise
    except Exception as e:
        log(f'Помилка натискання: {e}', ui_ref)
        state.stop_event.set()
        raise SessionCancelled('Не удалось выполнить нажатие') from e
    finally:
        if down:
            pydirectinput.keyUp(k)


def input_down(*,button,_pause=True):
    if str(button).startswith('key:'):
        name=direct_key(str(button)[4:])
        if name not in pydirectinput.KEYBOARD_MAPPING:raise SessionCancelled('Неподдерживаемая клавиша: '+name)
        pydirectinput.keyDown(name,_pause=_pause)
    else:
        pyautogui.mouseDown(button=button,_pause=_pause)


def input_up(*,button,_pause=True):
    if str(button).startswith('key:'):
        pydirectinput.keyUp(direct_key(str(button)[4:]),_pause=_pause)
    else:
        pyautogui.mouseUp(button=button,_pause=_pause)


def safe_mouse(action, button, ui_ref=None):
    try:
        controller = getattr(ui_ref,'auto_rod_controller',None) if ui_ref is not None else None
        guard = getattr(controller,'input_guard',None) if controller is not None else None
        # Releases must work after focus loss and Stop; they never wait on focus.
        if action == 'up':
            if guard is not None and guard.request(action,button):
                return
            input_up(button=button)
            return
        check_running()
        if not wait_for_focus(ui_ref, 30):
            state.stop_event.set()
            raise SessionCancelled('Не удалось дождаться фокуса игры')
        if action == 'down':
            if guard is not None and guard.request(action,button):
                return
            input_down(button=button)
        elif action == 'click':
            if str(button).startswith('key:'):
                human_press(str(button)[4:],ui_ref)
            else:
                pyautogui.click(button=button)
    except SessionCancelled:
        raise
    except Exception as e:
        log(f'Помилка мишки: {e}', ui_ref)
        if action != 'up':
            state.stop_event.set()
            raise SessionCancelled('Не удалось выполнить действие мышью') from e


def release_all(ui_ref, inc_r=True):
    raw_keys = [ui_ref.entry_rod1.get(), ui_ref.entry_rod2.get(), ui_ref.entry_rod3.get(
        ), ui_ref.entry_gb_key.get(), ui_ref.entry_net_key.get()]
    keys_to_release = ['h', 'left ctrl', 'left shift', 'alt', 'space', 'w', 'a', 's', 'd', 'r'] + [k for k in raw_keys if k and str(k).strip()]
    for k in keys_to_release:
        try:
            if keyboard.is_pressed(k):
                keyboard.release(k)
        except Exception:
            continue
    safe_mouse('up', ui_ref.entry_reel_btn.get(), ui_ref)
    if inc_r:
        safe_mouse('up', ui_ref.entry_pull_btn.get(), ui_ref)


def play_danger_sound(ui_ref):
    if ui_ref.check_danger_sound.get():
        try:
            winsound.Beep(1000, 250)
        except:
            pass


def smooth_move(dx, dy, steps=None):
    if steps is None:
        steps = random.randint(10, 20)
    for i in range(steps):
        curr_x = int(dx / steps)
        curr_y = int(dy / steps)
        if random.random() > 0.7:
            curr_x += random.choice([-1, 1])
        if random.random() > 0.7:
            curr_y += random.choice([-1, 1])
        try:
            pydirectinput.moveRel(curr_x, curr_y, relative=True)
        except:
            break
        time.sleep(random.uniform(0.005, 0.01) + i / steps * 0.005)


def switch_to_rod(n, ui_ref):
    if state.cur_rod_in_hand == str(n):
        return True
    log(f'Зміна на вудку {n}', ui_ref)
    human_press(str(n))
    state.cur_rod_in_hand = str(n)
    human_sleep(1.2)
    return True


def put_rod_on_stand(ui_ref):
    put_key = ui_ref.entry_put_key.get().strip() or 'alt'
    human_press(put_key)
    human_sleep(random.uniform(0.3, 0.6))
    state.cur_rod_in_hand = None
    log(f'Установка на подставку ({put_key})', ui_ref)
