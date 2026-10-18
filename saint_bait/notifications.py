"""Optional Discord/Telegram notifications and in-game chat."""

from . import state
from .controls import human_press
from .controls import wait_for_focus
from .logging_utils import log
from .paths import resource_path
from .settings import Const
from .settings import game_title
from mss import mss
from mss import tools
import json
import keyboard
import os
import pygetwindow as gw
import random
import requests
import threading
import time


def send_bot_msg(ui_ref, message, photo_path=None, is_danger=False):
    ds_url, tg_token, tg_chat = (ui_ref.entry_ds_webhook.get().strip(
        ), ui_ref.entry_tg_token.get().strip(), ui_ref.entry_tg_chat.get().strip())
    ds_id, tg_user = (ui_ref.entry_ds_mention.get().strip(), ui_ref.entry_tg_mention.get().strip())
    hrs, mins = (int(ui_ref.total_seconds // 3600), int(ui_ref.total_seconds % 3600 // 60))
    mentions = ''
    if is_danger:
        if ds_id:
            mentions += f'<@{ds_id}> '
        if tg_user:
            mentions += f"@{tg_user.replace('@', '')} "
    full_message = f"{mentions}{message}\n\nСтатистика:\nРиби всього: {ui_ref.total_fish}\nЗа сесію: {getattr(ui_ref, 'session_fish', 0)}\nТрофеїв: {getattr(ui_ref, 'trophy_count', 0)}\nКарток: {getattr(
        ui_ref, 'card_count', 0)}\nВуд. 1: {getattr(ui_ref, 'rod1_fish', 0)} | Вуд. 2: {getattr(ui_ref, 'rod2_fish', 0)} | Вуд. 3: {getattr(ui_ref, 'rod3_fish', 0)}\nЧас: {hrs}г {mins}хв"

    def send():
        if ds_url:
            try:
                if photo_path and os.path.exists(photo_path):
                    with open(photo_path, 'rb') as f:
                        requests.post(ds_url, data={'content': full_message}, files={'file': f})
                else:
                    requests.post(ds_url, json={'content': full_message})
            except:
                pass
        if tg_token and tg_chat:
            try:
                if photo_path and os.path.exists(photo_path):
                    with open(photo_path, 'rb') as f:
                        requests.post(f'https://api.telegram.org/bot{tg_token}/sendPhoto', data={
                                      'chat_id': tg_chat, 'caption': full_message}, files={'photo': f})
                else:
                    requests.post(
                        f'https://api.telegram.org/bot{tg_token}/sendMessage', data={'chat_id': tg_chat, 'text': full_message})
            except:
                pass
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except:
                pass
    threading.Thread(target=send, daemon=True).start()


def load_chat_messages():
    try:
        chat_path = resource_path(Const.CHAT_MESSAGES_FILE)
        if os.path.exists(chat_path):
            with open(chat_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
    except:
        pass
    return ['+++', 'ребята а на что сейчас клюёт', 'всем привет', 'как клёв?', 'кто на что ловит?', 'классная погода сегодня', 'а где тут нормальные места?', 'подскажите прикормку', 'я на фидер ловлю', 'а у вас что?']


def type_text(text, delay_range=(0.05, 0.15)):
    for char in text:
        keyboard.write(char)
        time.sleep(random.uniform(*delay_range))


def send_chat_message(ui_ref, message=None, send_screenshot=True):
    try:
        if message is None:
            messages = load_chat_messages()
            message = random.choice(messages)
        log(f'Відправка в чат: {message}', ui_ref)
        if not wait_for_focus(ui_ref, 3):
            log('Не вдалося отримати фокус гри для чату', ui_ref)
            return False
        human_press(Const.CHAT_OPEN_KEY, ui_ref)
        time.sleep(random.uniform(0.3, 0.6))
        type_text(message, delay_range=(0.03, 0.12))
        time.sleep(random.uniform(0.1, 0.3))
        human_press(Const.CHAT_SEND_KEY, ui_ref)
        time.sleep(random.uniform(0.2, 0.5))
        human_press(Const.CHAT_CLOSE_KEY, ui_ref)
        time.sleep(random.uniform(0.3, 0.6))
        log('Повідомлення відправлено', ui_ref)
        state.last_chat_time = time.time()
        screenshot_path = None
        if send_screenshot:
            try:
                wins = gw.getWindowsWithTitle(game_title)
                if wins:
                    win = wins[0]
                    screenshot_path = f'chat_screenshot_{int(time.time())}.png'
                    with mss() as sct:
                        rect = {'top': win.top, 'left': win.left,
                            'width': win.width, 'height': win.height}
                        img = sct.grab(rect)
                        tools.to_png(img.rgb, img.size, output=screenshot_path)
                    log(f'Скріншот збережено після відправки: {screenshot_path}', ui_ref)
            except Exception as e:
                log(f'Помилка скріншота: {e}', ui_ref)
                screenshot_path = None
        if ui_ref.entry_ds_webhook.get().strip():
            mention = ''
            ds_id = ui_ref.entry_ds_mention.get().strip()
            if ds_id:
                mention = f'<@{ds_id}> '
            discord_message = f'{mention}Повідомлення в чат: {message}'
            try:
                if screenshot_path and os.path.exists(screenshot_path):
                    with open(screenshot_path, 'rb') as f:
                        requests.post(ui_ref.entry_ds_webhook.get().strip(), data={
                                      'content': discord_message}, files={'file': f})
                    try:
                        os.remove(screenshot_path)
                    except:
                        pass
                else:
                    requests.post(ui_ref.entry_ds_webhook.get().strip(),
                                  json={'content': discord_message})
                log('Повідомлення відправлено в Discord з тегом', ui_ref)
            except Exception as e:
                log(f'Помилка відправки в Discord: {e}', ui_ref)
        return True
    except Exception as e:
        log(f'Помилка чату: {e}', ui_ref)
        try:
            human_press(Const.CHAT_CLOSE_KEY, ui_ref)
        except:
            pass
        return False
