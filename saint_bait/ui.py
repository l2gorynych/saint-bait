"""Desktop controls for Saint Bait; fishing behaviour lives in the engine.

The engine keeps the original entry/check widget API. Cached widget values and
the UI event queue let its worker read settings without calling Tcl/Tk.
"""

from __future__ import annotations

import os
import queue
import threading
import time
import json
import keyboard

import customtkinter as ctk
import pygetwindow as gw
from PIL import Image, ImageTk

from . import runtime as engine
from . import state
from .paths import data_path, resource_path
from .settings import Const, LANGS, config, game_title
from .rods import RodRegistry, PHASE_TEXT
from .telemetry.service import RodMonitor
from .controls import SessionCancelled, FocusGuard, is_game_focused
from .overlay import RodOverlay
from .game_input import input_token
from .runtime import resolve_mode
from .equipment_card import EquipmentArt,EquipmentCard
from .catch_journal import CatchJournal
from .community import CommunityService
from .community_ui import CommunityPanel
from .updates import UpdateService
from .paths import APP_DIR
from .telemetry.inventory_service import InventoryMonitor
from .deployment import UPDATE_REPOSITORY,SUPABASE_URL,SUPABASE_PUBLIC_KEY

UI_FONT='Myriad Pro'

COLORS = {
    "window": "#191919", "surface": "#333333", "raised": "#444444",
    "input": "#252525", "border": "#656565", "text": "#F2F2F2",
    "muted": "#B6B6B6", "accent": "#B1C82E", "accent_hover": "#C8DA48",
    "accent_dark": "#515C24", "danger": "#DA826C", "danger_hover": "#864F43",
}

SHELL_TEXT = {
    "RUS": {
        "subtitle": "Помощник рыболова · Russian Fishing 4", "ready": "Готов к работе",
        "running": "Ловля запущена", "stopping": "Завершаем работу…", "closing": "Закрытие…",
        "tab_fishing": "Ловля", "tab_modules": "Модули", "tab_keys": "Управление",
        "tab_notifications": "Связь", "tab_diagnostics": "Проверка",
        "log": "Журнал событий", "copy_log": "Копировать", "clear_log": "Очистить",
        "save": "Сохранить настройки", "saved": "Настройки сохранены",
        "volume_off": "Тест звука: выключен", "volume_on": "Тест звука: включён",
        "ocr_live": "Live OCR", "ocr_normal": "Область OCR · обычная",
        "ocr_casting": "Область OCR · кастинг", "no_line": "Без шнура (фидер)",
        "casting_rod": "Кастинговое удилище", "chat_messages": "Сообщения в игровой чат",
        "log_to_file": "Записывать журнал в файл", "runtime": "Распознавание текста",
        "runtime_hint": "В авторежиме донок данные читаются из памяти. Tesseract нужен только старым экранным режимам.",
        "choose_tesseract": "Выбрать tesseract.exe", "ocr_missing": "Нужен Tesseract OCR",
        "ocr_ready": "Tesseract найден", "tools": "Инструменты проверки",
        "tools_hint": "Проверьте звук и области распознавания перед ловлей. Игра должна быть открыта.",
        "notifications_hint": "Используются только ваши сохранённые реквизиты. Пустые поля отключают соответствующий канал.",
        "key_hint": "Названия кнопок мыши: left / right. Пустой слот удочки не используется.",
        "start_failed": "Не удалось запустить бота", "stop_failed": "Ошибка при остановке",
        "log_empty": "Журнал пока пуст", "log_copied": "Журнал скопирован",
    },
    "UKR": {
        "subtitle": "Помічник рибалки · Russian Fishing 4", "ready": "Готовий до роботи",
        "running": "Риболовлю розпочато", "stopping": "Завершення роботи…", "closing": "Закриття…",
        "tab_fishing": "Риболовля", "tab_modules": "Модулі", "tab_keys": "Керування",
        "tab_notifications": "Зв’язок", "tab_diagnostics": "Перевірка",
        "log": "Журнал подій", "copy_log": "Копіювати", "clear_log": "Очистити",
        "save": "Зберегти налаштування", "saved": "Налаштування збережено",
        "volume_off": "Тест звуку: вимкнено", "volume_on": "Тест звуку: увімкнено",
        "ocr_live": "Live OCR", "ocr_normal": "Область OCR · звичайна", "ocr_casting": "Область OCR · кастинг",
        "no_line": "Без шнура (фідер)", "casting_rod": "Кастингове вудилище",
        "chat_messages": "Повідомлення в ігровий чат", "log_to_file": "Записувати журнал у файл",
        "runtime": "Розпізнавання тексту", "runtime_hint": "Для читання дистанції потрібен Tesseract OCR. Шлях зберігається у налаштуваннях.",
        "choose_tesseract": "Вибрати tesseract.exe", "ocr_missing": "Потрібен Tesseract OCR", "ocr_ready": "Tesseract знайдено",
        "tools": "Інструменти перевірки", "tools_hint": "Перевірте звук і області розпізнавання перед риболовлею. Гра має бути відкрита.",
        "notifications_hint": "Використовуються ваші збережені реквізити. Порожні поля вимикають відповідний канал.",
        "key_hint": "Назви кнопок миші: left / right. Порожній слот вудки не використовується.",
        "start_failed": "Не вдалося запустити бота", "stop_failed": "Помилка зупинки",
        "log_empty": "Журнал поки порожній", "log_copied": "Журнал скопійовано",
    },
    "ENG": {
        "subtitle": "Fishing assistant · Russian Fishing 4", "ready": "Ready", "running": "Fishing is running",
        "stopping": "Stopping…", "closing": "Closing…", "tab_fishing": "Fishing", "tab_modules": "Modules",
        "tab_keys": "Controls", "tab_notifications": "Alerts", "tab_diagnostics": "Tools",
        "log": "Activity log", "copy_log": "Copy", "clear_log": "Clear", "save": "Save settings", "saved": "Settings saved",
        "volume_off": "Audio test: off", "volume_on": "Audio test: on", "ocr_live": "Live OCR",
        "ocr_normal": "OCR area · normal", "ocr_casting": "OCR area · casting", "no_line": "No line (feeder)",
        "casting_rod": "Casting rod", "chat_messages": "In-game chat messages", "log_to_file": "Save log to file",
        "runtime": "Text recognition", "runtime_hint": "Tesseract OCR is required to read distance. Its path is saved in settings.",
        "choose_tesseract": "Choose tesseract.exe", "ocr_missing": "Tesseract OCR required", "ocr_ready": "Tesseract found",
        "tools": "Diagnostic tools", "tools_hint": "Check audio and recognition areas before fishing. Keep the game open.",
        "notifications_hint": "Uses your saved credentials. Leave fields empty to disable a notification channel.",
        "key_hint": "Mouse button names: left / right. An empty rod slot is ignored.",
        "start_failed": "Unable to start", "stop_failed": "Unable to stop", "log_empty": "The log is empty", "log_copied": "Log copied",
    },
    "GER": {
        "subtitle": "Angelassistent · Russian Fishing 4", "ready": "Bereit", "running": "Angeln läuft",
        "stopping": "Wird angehalten…", "closing": "Wird geschlossen…", "tab_fishing": "Angeln", "tab_modules": "Module",
        "tab_keys": "Tasten", "tab_notifications": "Meldungen", "tab_diagnostics": "Prüfung",
        "log": "Ereignisprotokoll", "copy_log": "Kopieren", "clear_log": "Leeren", "save": "Einstellungen speichern", "saved": "Einstellungen gespeichert",
        "volume_off": "Audiotest: aus", "volume_on": "Audiotest: an", "ocr_live": "Live OCR",
        "ocr_normal": "OCR-Bereich · normal", "ocr_casting": "OCR-Bereich · Casting", "no_line": "Ohne Schnur (Feeder)",
        "casting_rod": "Castingrute", "chat_messages": "Nachrichten im Spielchat", "log_to_file": "Protokoll in Datei speichern",
        "runtime": "Texterkennung", "runtime_hint": "Tesseract OCR liest die Entfernung. Der Pfad wird in den Einstellungen gespeichert.",
        "choose_tesseract": "tesseract.exe auswählen", "ocr_missing": "Tesseract OCR erforderlich", "ocr_ready": "Tesseract gefunden",
        "tools": "Diagnosewerkzeuge", "tools_hint": "Ton und Erkennungsbereiche vor dem Angeln prüfen. Das Spiel muss geöffnet sein.",
        "notifications_hint": "Verwendet gespeicherte Zugangsdaten. Leere Felder deaktivieren den jeweiligen Kanal.",
        "key_hint": "Maustasten: left / right. Leere Rutenslots werden ignoriert.",
        "start_failed": "Start fehlgeschlagen", "stop_failed": "Anhalten fehlgeschlagen", "log_empty": "Das Protokoll ist leer", "log_copied": "Protokoll kopiert",
    },
    "POL": {
        "subtitle": "Asystent wędkarza · Russian Fishing 4", "ready": "Gotowy", "running": "Łowienie uruchomione",
        "stopping": "Zatrzymywanie…", "closing": "Zamykanie…", "tab_fishing": "Łowienie", "tab_modules": "Moduły",
        "tab_keys": "Klawisze", "tab_notifications": "Kontakt", "tab_diagnostics": "Testy",
        "log": "Dziennik zdarzeń", "copy_log": "Kopiuj", "clear_log": "Wyczyść", "save": "Zapisz ustawienia", "saved": "Ustawienia zapisane",
        "volume_off": "Test dźwięku: wył.", "volume_on": "Test dźwięku: wł.", "ocr_live": "Live OCR",
        "ocr_normal": "Obszar OCR · zwykły", "ocr_casting": "Obszar OCR · casting", "no_line": "Bez linki (feeder)",
        "casting_rod": "Wędka castingowa", "chat_messages": "Wiadomości na czacie gry", "log_to_file": "Zapisuj dziennik do pliku",
        "runtime": "Rozpoznawanie tekstu", "runtime_hint": "Tesseract OCR odczytuje odległość. Ścieżka jest zapisywana w ustawieniach.",
        "choose_tesseract": "Wybierz tesseract.exe", "ocr_missing": "Wymagany Tesseract OCR", "ocr_ready": "Znaleziono Tesseract",
        "tools": "Narzędzia diagnostyczne", "tools_hint": "Sprawdź dźwięk i obszary rozpoznawania przed łowieniem. Gra musi być otwarta.",
        "notifications_hint": "Używa zapisanych danych. Puste pola wyłączają dany kanał powiadomień.",
        "key_hint": "Przyciski myszy: left / right. Puste sloty wędek są pomijane.",
        "start_failed": "Nie udało się uruchomić", "stop_failed": "Nie udało się zatrzymać", "log_empty": "Dziennik jest pusty", "log_copied": "Dziennik skopiowany",
    },
    "CHN": {
        "subtitle": "钓鱼助手 · Russian Fishing 4", "ready": "准备就绪", "running": "正在钓鱼", "stopping": "正在停止…", "closing": "正在关闭…",
        "tab_fishing": "钓鱼", "tab_modules": "模块", "tab_keys": "控制", "tab_notifications": "通知", "tab_diagnostics": "诊断",
        "log": "活动日志", "copy_log": "复制", "clear_log": "清空", "save": "保存设置", "saved": "设置已保存",
        "volume_off": "声音测试：关", "volume_on": "声音测试：开", "ocr_live": "实时 OCR",
        "ocr_normal": "OCR 区域 · 普通", "ocr_casting": "OCR 区域 · 枪柄竿", "no_line": "无线模式（底钓）",
        "casting_rod": "枪柄竿", "chat_messages": "游戏聊天消息", "log_to_file": "将日志保存到文件",
        "runtime": "文字识别", "runtime_hint": "读取距离需要 Tesseract OCR。程序路径保存在设置中。",
        "choose_tesseract": "选择 tesseract.exe", "ocr_missing": "需要 Tesseract OCR", "ocr_ready": "已找到 Tesseract",
        "tools": "诊断工具", "tools_hint": "钓鱼前检查声音和识别区域。请先打开游戏。",
        "notifications_hint": "使用您已保存的凭据。留空可禁用对应的通知渠道。", "key_hint": "鼠标按键名称：left / right。空鱼竿栏位将被忽略。",
        "start_failed": "无法启动", "stop_failed": "无法停止", "log_empty": "日志为空", "log_copied": "日志已复制",
    },
}


for _language,_captions in {'RUS': ('Фидер', 'Спиннинг', 'Общее', 'Клавиши', 'Связь'), 'UKR': ('Фідер', 'Спінінг', 'Загальне', 'Клавіші', 'Зв’язок'), 'ENG': ('Feeder', 'Spinning', 'General', 'Controls', 'Alerts'), 'GER': ('Feeder', 'Spinnfischen', 'Allgemein', 'Tasten', 'Meldungen'), 'POL': ('Feeder', 'Spinning', 'Ogólne', 'Klawisze', 'Kontakt'), 'CHN': ('底钓', '路亚', '通用', '控制', '通知')}.items():
    SHELL_TEXT[_language].update(dict(zip(("tab_feeder","tab_spinning","tab_general","tab_keys","tab_notifications"),_captions)))


class CachedEntry(ctk.CTkEntry):
    """An ordinary editable entry whose get() is safe for the fishing worker."""

    def __init__(self, master, owner, **kwargs):
        self._owner = owner
        self._cached_value = ""
        self._value = ctk.StringVar(master=owner, value="")
        kwargs["textvariable"] = self._value
        super().__init__(master, **kwargs)
        self._value.trace_add("write", self._cache_value)

    def _cache_value(self, *_):
        self._cached_value = self._value.get()

    def get(self):
        return self._cached_value

    def insert(self, index, string):
        if threading.get_ident() != self._owner._ui_thread:
            position = len(self._cached_value) if index == "end" else int(index)
            self._cached_value = self._cached_value[:position] + str(string) + self._cached_value[position:]
            self._owner.dispatch(super().insert, index, string)
            return
        super().insert(index, string)

    def delete(self, first, last=None):
        if threading.get_ident() != self._owner._ui_thread:
            start = int(first)
            end = len(self._cached_value) if last == "end" else (int(last) if last is not None else start + 1)
            self._cached_value = self._cached_value[:start] + self._cached_value[end:]
            self._owner.dispatch(super().delete, first, last)
            return
        super().delete(first, last)


class CachedCheckBox(ctk.CTkCheckBox):
    def __init__(self, master, owner, **kwargs):
        self._cached_value = 1
        self._value = ctk.IntVar(master=owner, value=1)
        kwargs["variable"] = self._value
        super().__init__(master, **kwargs)
        self._value.trace_add("write", self._cache_value)

    def _cache_value(self, *_):
        self._cached_value = self._value.get()

    def get(self):
        return self._cached_value


class DispatchButton(ctk.CTkButton):
    def __init__(self, master, owner, **kwargs):
        self._owner = owner
        super().__init__(master, **kwargs)

    def configure(self, require_redraw=False, **kwargs):
        if threading.get_ident() != self._owner._ui_thread:
            self._owner.dispatch(super().configure, require_redraw=require_redraw, **kwargs)
            return
        super().configure(require_redraw=require_redraw, **kwargs)


class SaintBaitUI(ctk.CTk):
    """Main application window with an explicit, single-worker lifecycle."""

    def __init__(self):
        for file in ('MyriadPro-Regular.ttf','MyriadPro-Semibold.ttf','MyriadPro-Bold.ttf'):
            ctk.FontManager.load_font(resource_path('fonts/'+file))
        ctk.set_appearance_mode("dark")
        super().__init__()
        self._ui_thread = threading.get_ident()
        self._events = queue.Queue()
        self._lock = threading.RLock()
        self._closing = False
        self._stopping = False
        self._destroyed = False
        self._text_widgets = []
        self._tab_keys = []
        self._status_key = "ready"
        self.bot_thread = None
        self.auto_rod_controller = None
        self.rod_registry = RodRegistry(cache_path=data_path('rod-slots.json'))
        self.catch_journal=CatchJournal(data_path('catches.sqlite3'))
        self.rod_monitor = RodMonitor(self.rod_registry,self.catch_journal)
        self.inventory_monitor=InventoryMonitor(self.rod_registry,self.catch_journal)
        self.community=CommunityService(self.catch_journal,self.rod_registry,data_path('community-session.json'))
        self.updates=UpdateService(APP_DIR)
        self._stop_hotkey = None
        try:
            with open(resource_path('fish_names.json'),encoding='utf-8') as stream:
                self._fish_names = json.load(stream)
        except (OSError,ValueError):
            self._fish_names = {}
        self.camera_offset_y = 0
        self.total_daylight_wait = 0.0
        self.config = config
        self.community.configure(SUPABASE_URL,SUPABASE_PUBLIC_KEY)
        self.community.start()
        self.updates.check(UPDATE_REPOSITORY)
        self.fishing_mode = 'auto'
        self.entries_map, self.checks_map = {}, {}
        self.curr_lang = self.config.get("Settings", "lang", fallback="RUS")
        if self.curr_lang not in SHELL_TEXT:
            self.curr_lang = "RUS"
        self.total_fish = self.session_fish = self.trophy_count = self.card_count = 0
        self.rod1_fish = self.rod2_fish = self.rod3_fish = 0
        self.total_seconds, self.session_start = 0.0, None
        self.title("Saint Bait · Russian Fishing 4")
        self.geometry("880x940")
        self.minsize(820, 880)
        self.configure(fg_color=COLORS["window"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._app_icon = None
        self._apply_icon()
        self.after(300, self._apply_icon)
        self._build_header()
        self._build_statistics()
        self._build_settings()
        self._build_actions()
        self._build_log()
        self._load_configuration()
        self.rod_overlay = RodOverlay(self)
        self.refresh_stats_ui()
        self._refresh_runtime_status()
        self.after(75, self._drain_events)
        self.after(1000, self._tick_clock)
        self.after(300, self._tick_rods)

    def _apply_icon(self):
        if self._destroyed:
            return
        icon_path = resource_path("Podust.ico")
        try:
            self.iconbitmap(bitmap=icon_path, default=icon_path)
            if self._app_icon is None:
                with Image.open(icon_path) as source:
                    self._app_icon = ImageTk.PhotoImage(source.convert("RGBA").resize((32, 32)), master=self)
            self.iconphoto(True, self._app_icon)
        except Exception:
            pass

    def text(self, key, fallback=None):
        if key in SHELL_TEXT.get(self.curr_lang, {}):
            return SHELL_TEXT[self.curr_lang][key]
        return LANGS.get(self.curr_lang, {}).get(key, fallback or key)

    def _translated(self, widget, key, fallback=None):
        self._text_widgets.append((widget, key, fallback))
        widget.configure(text=self.text(key, fallback))
        return widget

    def _label(self, master, key, fallback=None, **kwargs):
        options = dict(font=(UI_FONT, 11), text_color=COLORS["muted"], anchor="w")
        options.update(kwargs)
        label = self._translated(ctk.CTkLabel(master, **options), key, fallback)
        return label

    def _button(self, master, key, command, fallback=None, **kwargs):
        options = dict(height=28, corner_radius=2, font=(UI_FONT, 11),
                       fg_color=COLORS["raised"], hover_color=COLORS["border"], text_color=COLORS["text"])
        options.update(kwargs)
        button = DispatchButton(master, owner=self, command=command, **options)
        return self._translated(button, key, fallback)

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 7))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="SAINT BAIT", font=(UI_FONT, 17, "bold"),
                     text_color=COLORS["text"], anchor="w").grid(row=0, column=0, sticky="w")
        self._label(header, "subtitle", font=(UI_FONT, 10)).grid(row=1, column=0, sticky="w")
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self.lbl_status = ctk.CTkLabel(right, text=self.text("ready"), font=(UI_FONT, 10, "bold"),
                                     text_color=COLORS["accent"], fg_color=COLORS["accent_dark"],
                                     corner_radius=6, height=23)
        self.lbl_status.pack(anchor="e", fill="x", pady=(0, 3))
        self.f_sw = ctk.CTkFrame(right, fg_color="transparent")
        self.f_sw.pack(anchor="e")
        self.btns = {}
        self._flag_images = {}
        for i, (code, caption, flag) in enumerate((("RUS", "RU", "ru"), ("UKR", "UA", "ua"), ("ENG", "EN", "gb"),
                                                   ("GER", "DE", "de"), ("POL", "PL", "pl"), ("CHN", "中文", "cn"))):
            try:
                with Image.open(resource_path(f"flags/{flag}.png")) as source:
                    flag_image = source.copy()
                self._flag_images[code] = ctk.CTkImage(light_image=flag_image, dark_image=flag_image, size=(22, 14))
            except OSError:
                self._flag_images[code] = None
            button = self._button(self.f_sw, code, lambda value=code: self.change_lang(value),
                                  fallback=caption, width=30, height=24, font=(UI_FONT, 10, "bold"))
            self._text_widgets.pop()  # Language names remain recognisable in every language.
            button.configure(text="" if self._flag_images[code] else caption, image=self._flag_images[code])
            button.grid(row=0, column=i, padx=(3, 0))
            self.btns[code] = button
        self._refresh_language_buttons()

    def _build_statistics(self):
        self.stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 5))
        self.stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="stat")
        stats = (("txt_total_fish", "lbl_total_fish", "fish_total", "Всего рыбы", COLORS["accent"]),
                 ("txt_session_fish", "lbl_session_fish", "session", "За сессию", COLORS["text"]),
                 ("txt_trophies", "lbl_trophy_count", "trophies", "Трофеи", "#E6C371"),
                 ("txt_cards", "lbl_card_count", "cards", "Карточки", "#B5A0E9"))
        for col, (label_attr, value_attr, key, fallback, color) in enumerate(stats):
            card = ctk.CTkFrame(self.stats_frame, fg_color=COLORS["surface"], corner_radius=2)
            card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 3, 0 if col == 3 else 3))
            label = self._label(card, key, fallback, font=(UI_FONT, 10))
            label.pack(side='left',padx=(9,4),pady=5)
            value = ctk.CTkLabel(card, text="0", text_color=color, font=(UI_FONT, 13, "bold"), height=22)
            value.pack(side='right',padx=(0,9),pady=5)
            setattr(self, label_attr, label)
            setattr(self, value_attr, value)
        details = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        # Preserve per-rod statistics for persistence; show the session timer
        # in this compact row instead of a second wall of counters.
        details.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(1, 0))
        details.grid_columnconfigure(6, weight=1)
        for i in range(1, 4):
            label = self._label(details, f"rod{i}_stats", f"Удочка {i}:", font=(UI_FONT, 10), height=20)
            value = ctk.CTkLabel(details, text="0", text_color=COLORS["text"], font=(UI_FONT, 10, "bold"), height=20)
            setattr(self, f"txt_rod{i}", label)
            setattr(self, f"lbl_rod{i}_fish", value)
        self.txt_work_time = self._label(details, "work_time", "Время работы:", font=(UI_FONT, 10), height=20)
        self.txt_work_time.grid(row=0, column=0, columnspan=5, sticky="e", padx=(0, 8))
        self.lbl_total_time = ctk.CTkLabel(details, text="00:00:00", text_color=COLORS["text"], font=("Consolas", 11), height=20)
        self.lbl_total_time.grid(row=0, column=5, columnspan=2, sticky="w")
        self.lbl_keepnet=ctk.CTkLabel(details,text='Садок — / —',font=(UI_FONT,11),height=20,
                                    text_color=COLORS['muted'])
        self.lbl_keepnet.grid(row=0,column=7,sticky='e',padx=(12,0))
        monitor = ctk.CTkFrame(self.stats_frame,fg_color='transparent')
        monitor.grid(row=2,column=0,columnspan=4,sticky='ew',pady=(6,0))
        monitor.grid_columnconfigure((0,1,2),weight=1,uniform='rod')
        self._rod_cards = []
        self._equipment_art=EquipmentArt()
        self._equipment_cards=[]
        for index in range(3):
            card = EquipmentCard(monitor,self._equipment_art,COLORS,UI_FONT,index)
            card.grid(row=0,column=index,sticky='nsew',padx=(0 if index==0 else 3,0))
            self._rod_cards.append((card.title,card.phase,card.detail))
            self._equipment_cards.append(card)

    def _build_settings(self):
        self.tabs = ctk.CTkTabview(self, fg_color=COLORS['surface'],corner_radius=2,
            segmented_button_fg_color=COLORS['surface'],segmented_button_selected_color=COLORS['accent_dark'],
            segmented_button_selected_hover_color=COLORS['border'],segmented_button_unselected_color=COLORS['surface'],
            segmented_button_unselected_hover_color=COLORS['raised'],text_color=COLORS['text'])
        self.tabs.grid(row=2,column=0,sticky='nsew',padx=12,pady=(0,7))
        self._pages={}
        for key in ('tab_fishing','tab_general','tab_keys','tab_notifications','Уловы'):
            name=self.text(key)
            tab=self.tabs.add(name)
            self._tab_keys.append((key,name))
            tab.grid_columnconfigure(0,weight=1)
            tab.grid_rowconfigure(0,weight=1)
            page=ctk.CTkScrollableFrame(tab,fg_color='transparent',corner_radius=0)
            page.grid(row=0,column=0,sticky='nsew')
            page.grid_columnconfigure((0,1),weight=1,uniform='form')
            self._pages[key]=page
        self.community_panel=CommunityPanel(self._pages['Уловы'],self,COLORS,UI_FONT)
        self.community_panel.grid(row=0,column=0,columnspan=2,sticky='ew')
        page=self._pages['tab_fishing']
        heading,group=self._group(page,'cast_settings','Заброс',0,0,span=2)
        self.feeder_settings=heading.master
        self._label(group,'automatic_tackle_hint','Тип снасти определяется автоматически. Снасти на подставках можно оставить как есть.',
                    wraplength=460,justify='left').grid(row=0,column=0,columnspan=2,sticky='w',padx=7,pady=5)
        try:cast_default=str(max(.1,min(8.,float(self.config.get('Settings','clip',fallback='8'))/10)))
        except ValueError:cast_default='0.8'
        self._fields(group,(("entry_clip","clip_m","clip_metres","Клипса (м)","8"),
            ("entry_feeder_slots","feeder_slots","feeder_slots","Слоты снастей (через запятую)","1,2,3")),start_row=1)
        self._label(group,'automatic_drag','Фрикцион подбирается автоматически по прочности снасти.',wraplength=460).grid(
            row=3,column=0,columnspan=2,sticky='w',padx=7,pady=5)
        heading,group=self._group(page,'food_set','Прикормка',1,0,span=2)
        self.groundbait_settings=heading.master
        self._checks(group,(("check_do_gb","do_gb","gb","Использовать прикормку",False),),columns=1)
        self._fields(group,(("entry_gb_key","gb_key","bait_slot","Слот прикормки (1–7)","5"),
            ("entry_gb_game_hours","gb_game_hours","h","Интервал (игровые часы)","12"),
            ("entry_gb_dur","gb_dur","bait_distance","Дистанция прикормки (м)","8")),start_row=1)
        heading,group=self._group(page,'retrieve_settings','Проводка',2,0,span=2)
        self.spinning_settings=heading.master
        self.spinning_settings.grid_remove()
        self._label(group,'spinning_hint','Возьмите спиннинг в руки. Окончание проводки и рыба определяются по данным игры.',
                    wraplength=460,justify='left').grid(row=0,column=0,columnspan=2,sticky='w',padx=7,pady=5)
        self._checks(group,(("check_jig_mode","jig_mode","jig_mode","Джиговая проводка",False),),columns=1)
        self.check_jig_mode.grid_configure(row=1)
        self._fields(group,(("entry_spinning_cast","spinning_cast_s","cast_hold","Сила заброса (с удержания)",cast_default),
            ("entry_jig_reel_time","jig_reel_time","jig_reel","Подмотка в цикле (с)","1.42"),
            ("entry_jig_pause_time","jig_pause_time","jig_pause","Пауза в цикле (с)","2.58")),start_row=2)
        page=self._pages['tab_general']
        _,group=self._group(page,'session_settings','Сессия',0,0,span=2)
        self._fields(group,(("entry_stop_time","stop_time","session_limit_120","Лимит сессии (мин, не более 120; 0 — 120)","120"),))
        self._checks(group,(("check_auto_flashlight","auto_flashlight","auto_flashlight","Автофонарик",False),
            ("check_stop_at_night","stop_at_night","stop_at_night","Пауза спиннинга ночью",False),
            ("check_log_to_file","log_to_file","log_to_file","Журнал в файл",True)),columns=1)
        for index,widget in enumerate((self.check_auto_flashlight,self.check_stop_at_night,self.check_log_to_file)):
            widget.grid_configure(row=1+index)
        _,group=self._group(page,'food','Еда',1,0,span=2)
        self._checks(group,(("check_do_cons","auto_food","food_auto","Питание по сытости",True),),columns=1)
        self._fields(group,(("entry_food_slot","food_slot","food_slot","Слот еды (1–7)","4"),),start_row=1)
        self.lbl_nutrition=ctk.CTkLabel(group,text='Сытость: ожидание данных',text_color=COLORS['muted'])
        self.lbl_nutrition.grid(row=2,column=0,columnspan=2,sticky='w',padx=7,pady=5)
        page=self._pages['tab_keys']
        _,group=self._group(page,'game_controls','Клавиши из игры',0,0,span=2)
        self._fields(group,(("entry_rod1","rod1","rod1_stats","Слот снасти 1",""),
            ("entry_rod2","rod2","rod2_stats","Слот снасти 2",""),
            ("entry_rod3","rod3","rod3_stats","Слот снасти 3",""),
            ("entry_net_key","net_key","net","Подсак","t"),
            ("entry_pull_btn","pull_btn","rmb","Поднять удочку",""),
            ("entry_reel_btn","reel_btn","lmb","Подмотка / заброс",""),
            ("entry_put_key","put_key","put_rod","Подставка","")))
        self._game_key_fields={'slot1':self.entry_rod1,'slot2':self.entry_rod2,'slot3':self.entry_rod3,
            'pull':self.entry_pull_btn,'reel':self.entry_reel_btn,'stand':self.entry_put_key}
        for widget in self._game_key_fields.values():widget.configure(state='disabled')
        self.lbl_memory_status=ctk.CTkLabel(page,text='',wraplength=460,justify='left',text_color=COLORS['muted'])
        self.lbl_memory_status.grid(row=1,column=0,columnspan=2,sticky='w',padx=10,pady=6)
        self._label(page,'stop_key_hint','F8 — экстренная остановка. Переназначайте игровые клавиши в игре.',
                    wraplength=460,justify='left').grid(row=2,column=0,columnspan=2,sticky='w',padx=10,pady=6)
        page=self._pages['tab_notifications']
        _,group=self._group(page,'notif_set','Каналы уведомлений',0,0,span=2)
        self._checks(group,(("check_catch_alerts","catch_alerts","catch_alerts","Отправлять отчёты об улове",False),),columns=1)
        self._fields(group,(("entry_ds_webhook","discord_webhook","ds_webhook","Discord Webhook",""),
            ("entry_ds_mention","ds_mention_id","ds_id","Discord ID",""),
            ("entry_tg_token","tg_token","tg_token","Telegram Bot Token",""),
            ("entry_tg_chat","tg_chat_id","tg_chat","Telegram Chat ID",""),
            ("entry_tg_mention","tg_mention_user","tg_user","Telegram Username","")),start_row=1)
        self.entry_tg_token.configure(show='•')
        self.entry_ds_webhook.configure(show='•')

    def _group(self, master, key, fallback, row, column, span=1):
        card = ctk.CTkFrame(master, fg_color=COLORS["surface"], border_width=1,border_color=COLORS['border'],corner_radius=2)
        card.grid(row=row, column=column, columnspan=span, sticky="nsew", padx=3, pady=(2, 6))
        card.grid_columnconfigure(0, weight=1)
        title = self._label(card, key, fallback, text_color=COLORS["text"], font=(UI_FONT, 12, "bold"))
        title.grid(row=0, column=0, sticky="ew", padx=12, pady=(5, 3))
        group = ctk.CTkFrame(card, fg_color="transparent")
        group.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        group.grid_columnconfigure((0, 1), weight=1, uniform="field")
        return title, group

    def _fields(self, master, definitions, start_row=0):
        for index, (attribute, key, lang_key, fallback, default) in enumerate(definitions):
            entry = self.fld(master, lang_key, default, start_row + index // 2, index % 2, fallback)
            setattr(self, attribute, entry)
            self.entries_map[key] = entry

    def fld(self, master, label_key, default, row, column, fallback=None):
        holder = ctk.CTkFrame(master, fg_color="transparent")
        holder.grid(row=row, column=column, sticky="ew", padx=5, pady=3)
        label = self._label(holder, label_key, fallback, font=(UI_FONT, 11), wraplength=205)
        label.pack(anchor="w", fill="x", pady=(0, 2))
        entry = CachedEntry(holder, owner=self, height=30, corner_radius=1, font=(UI_FONT, 12),
                            fg_color=COLORS["input"], border_color=COLORS["border"], text_color=COLORS["text"])
        entry.insert(0, default)
        entry.pack(fill="x")
        self.setup_paste(entry)
        return entry

    def _checks(self, master, definitions, columns=2):
        for index, (attribute, key, lang_key, fallback, selected) in enumerate(definitions):
            checkbox = self.chk(master, lang_key, index // columns, index % columns, fallback)
            if columns == 1:
                checkbox.grid_configure(columnspan=2)
            if not selected:
                checkbox.deselect()
            else:
                checkbox.select()
            setattr(self, attribute, checkbox)
            self.checks_map[key] = checkbox

    def chk(self, master, key, row, column, fallback=None):
        checkbox = CachedCheckBox(master, owner=self, text=self.text(key, fallback), font=(UI_FONT, 11),
                                  checkbox_width=17, checkbox_height=17, corner_radius=1,
                                  border_width=2, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                                  checkmark_color=COLORS["window"], text_color=COLORS["text"], border_color=COLORS['border'])
        checkbox.grid(row=row, column=column, sticky="w", padx=6, pady=5)
        self._text_widgets.append((checkbox, key, fallback))
        return checkbox

    def _build_actions(self):
        self.btn_f = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_f.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 7))
        self.btn_f.grid_columnconfigure(0, weight=1)
        self.btn_save = self._button(self.btn_f, "save", self.save_settings, width=160, height=32)
        self.btn_save.grid(row=0, column=0, sticky="w")
        self.btn_start = self._button(self.btn_f, "start", self.start_logic, "СТАРТ", width=120, height=34,
                                      font=(UI_FONT, 12, "bold"), fg_color=COLORS["accent"],
                                      hover_color=COLORS["accent_hover"], text_color=COLORS["window"])
        self.btn_start.grid(row=0, column=1, padx=(6, 7))
        self.button_start = self.btn_start  # Original engine compatibility.
        self.btn_stop = self._button(self.btn_f, "stop", self.stop_logic, "СТОП", width=95, height=34,
                                     fg_color=COLORS['raised'], hover_color=COLORS["danger_hover"], state="disabled")
        self.btn_stop.grid(row=0, column=2)

    def _build_log(self):
        panel = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=2)
        panel.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        self._label(panel, "log", text_color=COLORS["text"], font=(UI_FONT, 11, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=3)
        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="e", padx=7, pady=3)
        self.btn_copy_log = self._button(controls, "copy_log", self.copy_log, width=80, height=24)
        self.btn_copy_log.pack(side="left", padx=(0, 5))
        self.btn_clear_log = self._button(controls, "clear_log", self.clear_log, width=72, height=24)
        self.btn_clear_log.pack(side="left")
        self.log_box = ctk.CTkTextbox(panel, height=62, font=("Consolas", 10), fg_color=COLORS["input"],
                                    text_color=COLORS['muted'], corner_radius=1, border_width=0, state="disabled", wrap="word")
        self.log_box.grid(row=1, column=0, columnspan=2, sticky="ew", padx=7, pady=(0, 7))

    @staticmethod
    def setup_paste(widget):
        def paste(_event):
            try:
                value = widget.clipboard_get()
                try:
                    widget.delete("sel.first", "sel.last")
                except Exception:
                    pass
                widget.insert("insert", value)
            except Exception:
                pass
            return "break"
        widget.bind("<Control-v>", paste)
        widget.bind("<Control-V>", paste)

    def _load_configuration(self):
        for section in ("Settings", "Keys", "Bots", "Spinning"):
            if self.config.has_section(section):
                for key, value in self.config.items(section):
                    if key in self.entries_map:
                        self.entries_map[key].delete(0, "end")
                        self.entries_map[key].insert(0, value)
        for section in ("Modules", "Spinning"):
            if self.config.has_section(section):
                for key, value in self.config.items(section):
                    if key in self.checks_map:
                        self.checks_map[key].select() if value == "1" else self.checks_map[key].deselect()
        for attribute, key, cast in (
            ("total_fish", "total_fish", int), ("trophy_count", "total_trophies", int),
            ("card_count", "total_cards", int), ("total_seconds", "total_seconds", float),
            ("rod1_fish", "rod1_fish", int), ("rod2_fish", "rod2_fish", int), ("rod3_fish", "rod3_fish", int),
        ):
            try:
                setattr(self, attribute, cast(self.config.get("Statistics", key, fallback="0")))
            except (ValueError, TypeError):
                setattr(self, attribute, cast(0))

    @staticmethod
    def _entry_section(key):
        if any(part in key for part in ("key", "btn", "rod", "net")):
            return "Keys"
        if any(part in key for part in ("webhook", "tg_", "ds_", "mention")):
            return "Bots"
        if key in ("spinning_cast_s", "jig_reel_time", "jig_pause_time"):
            return "Spinning"
        return "Settings"

    def _write_configuration(self):
        temporary = data_path("podust.properties.tmp")
        with open(temporary, "w", encoding="utf-8") as destination:
            self.config.write(destination)
        os.replace(temporary, Const.CFG_FILE)

    def _store_settings(self):
        with self._lock:
            for section in ("Settings", "Keys", "Modules", "Bots", "Statistics", "Spinning"):
                if not self.config.has_section(section):
                    self.config.add_section(section)
            self.config.set("Settings", "lang", self.curr_lang)
            self.config.set("Settings", "mode", self.fishing_mode)
            for key, widget in self.entries_map.items():
                self.config.set(self._entry_section(key), key, str(widget.get()))
            for key, widget in self.checks_map.items():
                section = "Spinning" if key in ("spinning", "stop_at_night", "jig_mode", "casting_rod") else "Modules"
                self.config.set(section, key, "1" if widget.get() else "0")
            self._write_configuration()

    def save_settings(self):
        try:
            self._store_settings()
            engine.log(self.text("saved"), self)
        except Exception as error:
            engine.log(f"{self.text('start_failed')}: {error}", self)

    def _refresh_language_buttons(self):
        for code, button in self.btns.items():
            active = code == self.curr_lang
            button.configure(fg_color=COLORS["accent_dark"] if active else COLORS["raised"],
                             text_color=COLORS["accent"] if active else COLORS["muted"])

    def change_lang(self, choice):
        if choice not in SHELL_TEXT:
            return
        self.curr_lang = choice
        for widget, key, fallback in self._text_widgets:
            widget.configure(text=self.text(key, fallback))
        updated = []
        for key, old_name in self._tab_keys:
            new_name = self.text(key)
            if old_name != new_name:
                self.tabs.rename(old_name, new_name)
            updated.append((key, new_name))
        self._tab_keys = updated
        self._refresh_language_buttons()
        self._set_status(self._status_key)
        self._refresh_runtime_status()
        try:
            self._store_settings()
        except Exception as error:
            engine.log(f"{self.text('start_failed')}: {error}", self)

    def _refresh_runtime_status(self):
        scene=self.rod_registry.scene()
        if scene is not None and scene.keepnet_count is not None and scene.keepnet_capacity is not None:
            full=scene.keepnet_count>=scene.keepnet_capacity
            self.lbl_keepnet.configure(text=f'Садок {scene.keepnet_count} / {scene.keepnet_capacity}'+(' · полон' if full else ''),
                                      text_color=COLORS['danger'] if full else COLORS['text'])
        else:self.lbl_keepnet.configure(text='Садок — / —',text_color=COLORS['muted'])
        self.lbl_memory_status.configure(text=('Данные игры подключены. Клавиши синхронизированы.' if scene else self.rod_registry.error or 'Ожидание данных игры'))

    def _sync_game_controls(self):
        scene=self.rod_registry.scene()
        if scene:
            bindings=dict(scene.bindings)
            for name,widget in self._game_key_fields.items():
                value=bindings.get(name,'')
                if name in ('reel','pull') and value:value=input_token(value)
                if value!=widget.get():
                    widget.configure(state='normal')
                    widget.delete(0,'end')
                    widget.insert(0,value)
                    widget.configure(state='disabled')
        self._refresh_runtime_status()

    def dispatch(self, callback, *args, **kwargs):
        if not self._destroyed:
            self._events.put((callback, args, kwargs))

    def _drain_events(self):
        if self._destroyed:
            return
        for _ in range(250):
            try:
                callback, args, kwargs = self._events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception as error:
                print(f"UI event error: {error}")
            if self._destroyed:
                return
        if not self._destroyed:
            self.after(75, self._drain_events)

    def append_log(self, message):
        self.dispatch(self._append_log, str(message))

    def update_log(self, message):
        self.append_log(message)

    def _append_log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        # Keep a long session responsive; the complete log remains on disk when enabled.
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 3000:
            self.log_box.delete("1.0", f"{lines - 2500}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def copy_log(self):
        content = self.log_box.get("1.0", "end-1c")
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            engine.log(self.text("log_copied"), self)
        else:
            engine.log(self.text("log_empty"), self)

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def refresh_stats_ui(self):
        if threading.get_ident() != self._ui_thread:
            self.dispatch(self.refresh_stats_ui)
            return
        with self._lock:
            for label, value in ((self.lbl_total_fish, self.total_fish), (self.lbl_session_fish, self.session_fish),
                                 (self.lbl_trophy_count, self.trophy_count), (self.lbl_card_count, self.card_count),
                                 (self.lbl_rod1_fish, self.rod1_fish), (self.lbl_rod2_fish, self.rod2_fish),
                                 (self.lbl_rod3_fish, self.rod3_fish)):
                label.configure(text=str(value))
            elapsed = self.total_seconds + (time.time() - self.session_start if self.session_start is not None else 0)
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.lbl_total_time.configure(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _tick_clock(self):
        if self._destroyed:
            return
        self.refresh_stats_ui()
        self.after(1000, self._tick_clock)

    def _tick_rods(self):
        if self._destroyed or self._closing:
            return
        enabled = True
        self._sync_game_controls()
        scene=self.rod_registry.scene()
        if scene is not None and scene.satiety is not None:
            self.lbl_nutrition.configure(text=f'Сытость {scene.satiety:.0%} · энергия {scene.energy:.0%}')
        if enabled:
            self.rod_monitor.start()
            self.inventory_monitor.start()
        else:
            self.rod_monitor.stop()
        items = self.rod_registry.snapshot() if enabled else ()
        selected_kind=next((item.kind for item in items if item.active),None)
        spinning=selected_kind=='spinning' and not any(item.on_rest and item.kind=='feeder' for item in items)
        if spinning!=getattr(self,'_show_spinning_settings',None):
            self._show_spinning_settings=spinning
            if spinning:
                self.feeder_settings.grid_remove();self.groundbait_settings.grid_remove();self.spinning_settings.grid()
            else:
                self.spinning_settings.grid_remove();self.feeder_settings.grid();self.groundbait_settings.grid()
        lines = []
        kinds = {'feeder':'Донная','float':'Поплавочная','spinning':'Спиннинговая'}
        for index,(title,phase,detail) in enumerate(self._rod_cards):
            self._equipment_cards[index].update_equipment(items[index] if index<len(items) else None)
            if index>=len(items):
                title.configure(text=f'Снасть {index+1}')
                phase.configure(text=('Нет снасти' if items else self.rod_registry.error or 'Снасти не обнаружены')
                                if enabled else 'Ручные настройки',text_color=COLORS['muted'])
                detail.configure(text='')
                continue
            item = items[index]
            key = (' · '+item.slot_key) if item.slot_key else ' · слот ?'
            title.configure(text=kinds.get(item.kind,'Снасть')+key)
            phase.configure(text=PHASE_TEXT[item.phase],text_color=COLORS['text'])
            if item.hooked:
                species = self._fish_names.get(item.species,'Вид неизвестен')
                weight = f'{item.weight_g/1000:.3f}'.rstrip('0').rstrip('.').replace('.',',')+' кг' if item.weight_g else 'вес неизвестен'
                extra = species+' · '+weight
            else:
                extra = 'В руках' if item.active else 'На подставке' if item.on_rest else ''
            if item.memory_metrics:
                if item.line_m is not None:
                    extra += f' · {item.line_m:.1f} м'
                if item.load_fraction is not None:
                    extra += f'\nНагрузка {item.load_fraction*100:.0f}%'
                if item.drag_setting is not None:
                    extra += f' · Ф{item.drag_setting}'
                if item.clip_m is not None:extra += f' · клипса {item.clip_m} м'
                if item.drag_locked:
                    extra += ' · тормоз затянут'
            detail.configure(text=extra)
            from .hud import compact_line
            lines.append(compact_line(item,self._fish_names,index+1))
        self.rod_overlay.update(self.rod_registry.process_id(),lines)
        self.community_panel.refresh()
        self.after(500,self._tick_rods)

    def reset_session_stats(self):
        with self._lock:
            self.session_fish = self.rod1_fish = self.rod2_fish = self.rod3_fish = 0
            self.session_start = time.time()
        self.refresh_stats_ui()

    def _store_statistics(self):
        if not self.config.has_section("Statistics"):
            self.config.add_section("Statistics")
        for key, value in (("total_fish", self.total_fish), ("total_seconds", round(self.total_seconds, 2)),
                           ("total_trophies", self.trophy_count), ("total_cards", self.card_count),
                           ("rod1_fish", self.rod1_fish), ("rod2_fish", self.rod2_fish), ("rod3_fish", self.rod3_fish)):
            self.config.set("Statistics", key, str(value))
        self._write_configuration()

    def update_stats(self, fish_inc=0, is_t=False, is_trophy=False, is_card=False, rod_idx=None):
        with self._lock:
            now = time.time()
            if self.session_start is not None:
                self.total_seconds += now - self.session_start
                self.session_start = now
            self.total_fish += fish_inc
            self.session_fish += fish_inc
            self.trophy_count += int(bool(is_t or is_trophy))
            self.card_count += int(bool(is_card))
            if rod_idx in (0, 1, 2):
                attribute = f"rod{rod_idx + 1}_fish"
                setattr(self, attribute, getattr(self, attribute) + fish_inc)
            try:
                self._store_statistics()
            except OSError as error:
                self.append_log(f"Statistics save error: {error}")
        self.refresh_stats_ui()

    def save_stats_to_cfg(self):
        with self._lock:
            self._store_statistics()

    def _set_status(self, key):
        self._status_key = key
        self.lbl_status.configure(text=self.text(key),
                                  text_color="#E6C371" if key in ("stopping", "closing", "ocr_missing") else COLORS["accent"])

    def start_logic(self):
        if self._closing or self._stopping or (self.bot_thread and self.bot_thread.is_alive()):
            return
        try:
            if self.rod_registry.scene() is None:
                engine.log('Дождитесь подключения данных игры.',self)
                return
            self._sync_game_controls()
            mode,rods=resolve_mode(self.fishing_mode,self.rod_registry.snapshot())
            required=('reel','pull','net')+(('stand',) if mode=='feeder' else ())
            bindings=dict(self.rod_registry.scene().bindings)
            missing=[name for name in required if not bindings.get(name)]
            if missing:
                engine.log('Назначьте в игре управление: '+', '.join(missing),self)
                return
            if 'f8' in bindings.values():
                engine.log('F8 занят экстренной остановкой бота. Измените эту игровую привязку.',self)
                return
            self._store_settings()
            # Capture the user's view before activating the game can move its
            # mouse. This exact world direction is the casting anchor.
            self.cast_start_scene=self.rod_registry.scene()
            self.total_daylight_wait = 0.0
            self.reset_session_stats()
            try:
                windows = [window for window in gw.getWindowsWithTitle(game_title) if is_game_focused(window,self)]
                if len(windows)!=1:
                    raise SessionCancelled('Окно процесса игры не определено однозначно')
                windows[0].activate()
            except SessionCancelled:
                raise
            except Exception:
                pass
            state.stop_event.clear()
            self._stop_hotkey = keyboard.add_hotkey('f8',self.stop_logic,suppress=False)
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self._set_status("running")
            self.bot_thread = threading.Thread(target=self._run_engine, name="SaintBait-Fishing", daemon=True)
            self.bot_thread.start()
            engine.log(self.text("bot_start", "Бот запущен"), self)
        except Exception as error:
            engine.log(f"{self.text('start_failed')}: {error}", self)
            self.stop_logic()

    def _run_engine(self):
        focus_guard = FocusGuard(self)
        try:
            focus_guard.start()
            engine.core_loop(self)
        except SessionCancelled as error:
            engine.log(str(error),self)
        except Exception as error:
            engine.log(f"{self.text('start_failed')}: {error}", self)
        finally:
            state.stop_event.set()
            focus_guard.stop()
            controller = self.auto_rod_controller
            if controller is not None:
                controller.stop()
            try:
                engine.release_all(self)
            except Exception:
                pass
            self.dispatch(self._worker_finished, threading.current_thread())

    def _worker_finished(self, worker):
        if self.bot_thread is worker and not self._stopping:
            self._begin_stop()

    def stop_logic(self):
        # This method is also called by the engine. Never join the calling worker.
        state.stop_event.set()
        if threading.get_ident() != self._ui_thread:
            self.dispatch(self._worker_finished, threading.current_thread())
            return
        self._begin_stop()

    def _begin_stop(self):
        if self._stopping:
            return
        self._stopping = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        self._set_status("closing" if self._closing else "stopping")
        try:
            engine.release_all(self)
        except Exception as error:
            engine.log(f"{self.text('stop_failed')}: {error}", self)
        self._await_worker()

    def _await_worker(self):
        if self.bot_thread and self.bot_thread.is_alive():
            self.after(100, self._await_worker)
            return
        self._finish_stop()

    def _finish_stop(self):
        if self._stop_hotkey is not None:
            keyboard.remove_hotkey(self._stop_hotkey)
            self._stop_hotkey = None
        self.auto_rod_controller = None
        with self._lock:
            if self.session_start is not None:
                self.update_stats()
            self.session_start = None
        # Reset exactly the original Stop state, after the old worker exits.
        for attribute, value in {
            "first_run": True, "is_casting": False, "cur_rod_in_hand": None,
            "pending_bite": False, "hook_performed": False, "state": 0,
            "danger_was_triggered": False, "t_pull": 0.0, "t_dist_reached": None,
            "spin_offset_x": 0, "spin_offset_y": 0, "spin_walk_offset": 0,
            "spin_walk_keys": [], "net_used": False, "jig_started": False,
            "first_chat_sent": False, "first_chat_delay": 0, "chat_start_time": 0,
            "no_line_lift_done": False, "feed_tremor_offset_x": 0, "feed_tremor_offset_y": 0,
            "feed_tremor_history": [], "last_feed_tremor_time": 0,
            "no_line_flashlight_on": False, "no_line_last_flashlight_check": 0,
        }.items():
            setattr(state, attribute, value)
        self.bot_thread = None
        self._stopping = False
        try:
            self._store_settings()
        except OSError as error:
            self.append_log(f"Settings save error: {error}")
        self.refresh_stats_ui()
        engine.log(self.text("bot_stop", "Бот остановлен"), self)
        if self._closing:
            self._finish_close()
            return
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_status("ready")

    def on_closing(self):
        if self._closing:
            return
        self._closing = True
        self.community.stop()
        self.rod_monitor.stop()
        self.inventory_monitor.stop()
        self.stop_logic()

    def _finish_close(self):
        try:
            self.save_stats_to_cfg()
            self._store_settings()
        except OSError as error:
            print(f"Settings save error: {error}")
        try:self.updates.schedule_install()
        except (OSError,ValueError) as error:print('Update postponed:',type(error).__name__)
        self._destroyed = True
        self.destroy()

