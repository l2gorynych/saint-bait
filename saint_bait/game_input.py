"""Input uses the game's bindings; all held tackle inputs pass the load guard."""
from .controls import human_press,safe_mouse,SessionCancelled,wait_for_focus,check_running


def input_token(token):
    return token[6:] if token.startswith('mouse:') else 'key:'+token


class GameInput:
    def __init__(self,ui,bindings,overrides=None):
        self.ui=ui
        self.bindings=dict(bindings)
        self.overrides=dict(overrides or {})
        self._holds=set()

    def token(self,action):
        value=self.overrides.get(action,self.bindings.get(action))
        if not value:
            raise SessionCancelled('В игре не назначено управление: '+action)
        return value

    def press(self,action):
        modifier=None if action in self.overrides else self.bindings.get(action+'_modifier')
        if not modifier:
            human_press(self.token(action),self.ui)
            return
        import keyboard
        import pydirectinput
        from .bindings import direct_key
        if keyboard.is_pressed(modifier):
            raise SessionCancelled('Отпустите модификатор управления: '+modifier)
        self.release()
        check_running()
        if not wait_for_focus(self.ui,2):raise SessionCancelled('Нет фокуса игры для сочетания клавиш')
        try:
            pydirectinput.keyDown(direct_key(modifier),_pause=False)
            human_press(self.token(action),self.ui)
        finally:
            pydirectinput.keyUp(direct_key(modifier),_pause=False)

    def press_token(self,token):
        if not token:raise SessionCancelled('Не определена клавиша кнопки игры')
        human_press(token,self.ui)

    def hold(self,action,pressed):
        if (action in self._holds)==bool(pressed):return
        safe_mouse('down' if pressed else 'up',input_token(self.token(action)),self.ui)
        if pressed:self._holds.add(action)
        else:self._holds.discard(action)

    def release(self):
        self.hold('reel',False)
        self.hold('pull',False)

    def adjust_drag(self,direction):
        import keyboard
        if direction not in (-1,1):raise ValueError('Expected one drag step')
        modifier=self.bindings.get('speed_modifier')
        if not modifier or modifier.startswith('mouse:'):
            raise SessionCancelled('Не определена клавиша режима скорости катушки')
        if keyboard.is_pressed(modifier):
            raise SessionCancelled('Отпустите клавишу изменения скорости катушки')
        token=self.token('drag_up' if direction>0 else 'drag_down')
        if token in (v for k,v in self.bindings.items() if k not in ('drag_up','drag_down') and not k.endswith('_modifier')):
            raise SessionCancelled('Клавиша фрикциона совпадает с другим действием')
        self.release()
        action='drag_up' if direction>0 else 'drag_down'
        if self.bindings.get(action+'_modifier') and self.bindings.get(action+'_modifier')==self.bindings.get('stand'):
            # RF4 also regulates the brake by the unmodified wheel. Alt can
            # otherwise start the stand animation before the keypad chord.
            # One notch was verified against the native brake step; callers
            # acknowledge exactly one step before allowing another input.
            import pyautogui
            check_running()
            if not wait_for_focus(self.ui,2):raise SessionCancelled('Нет фокуса игры для фрикциона')
            pyautogui.scroll(direction,_pause=False)
        else:
            self.press(action)

    def move_view(self,dx,dy):
        import pydirectinput
        self.release()
        check_running()
        if not wait_for_focus(self.ui,2):raise SessionCancelled('Нет фокуса игры для поворота камеры')
        check_running()
        pydirectinput.moveRel(int(dx),int(dy),relative=True,_pause=False)

    def adjust_clip(self,direction):
        # RF4's fixed reel-clip chord from its in-game help. It is distinct
        # from the freely remappable reel brake and R+wheel speed commands.
        import pydirectinput
        if direction not in (-1,1):raise ValueError('Expected one clip step')
        self.release()
        check_running()
        if not wait_for_focus(self.ui,2):raise SessionCancelled('Нет фокуса игры для клипсы')
        try:
            pydirectinput.keyDown('ctrlleft',_pause=False)
            human_press('add' if direction>0 else 'subtract',self.ui)
        finally:
            pydirectinput.keyUp('ctrlleft',_pause=False)
