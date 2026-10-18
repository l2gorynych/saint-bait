"""Configuration and asset names shared by the UI and fishing modules."""

import configparser
import json
from pathlib import Path
import shutil

from .paths import data_path, resource_path


class Const:
    CFG_FILE = data_path("podust.properties")
    TESS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    G_TITLE = "Russian Fishing 4"
    F_IMG, D_IMG, DG_IMG = "fish_icon.png", "done_icon.png", "danger_icon.png"
    LOCK_IMG, T_IMG, T2_IMG = "lock_icon.png", "trophy_icon.png", "trophy2_icon.png"
    CD_IMG, COMMON_IMG, CLOSE_IMG = "card_icon.png", "common.png", "close.png"
    STATS_SECTION = "Statistics"
    PUT_ROD_KEY = "alt"
    OCR_Y_START, OCR_Y_END = 0.915, 0.930
    OCR_X_START, OCR_X_END = 0.531, 0.547
    OCR_X_START_CASTING, OCR_X_END_CASTING = 0.557, 0.573
    LOCK_Y_START, LOCK_Y_END = 0.88, 0.91
    LOCK_X_START, LOCK_X_END = 0.53, 0.55
    CHAT_OPEN_KEY, CHAT_CLOSE_KEY, CHAT_SEND_KEY = "q", "esc", "enter"
    CHAT_MESSAGES_FILE = "chat.json"
    CHAT_SEND_CHANCE = 0.03
    CHAT_MIN_INTERVAL = 1800


DEFAULTS = {
    "Paths": {"tesseract_path": Const.TESS_PATH, "game_title": Const.G_TITLE},
    "Images": {
        "fish_icon": Const.F_IMG, "done_icon": Const.D_IMG,
        "danger_icon": Const.DG_IMG, "lock_icon": Const.LOCK_IMG,
        "trophy_icon": Const.T_IMG, "trophy2_icon": Const.T2_IMG,
        "card_icon": Const.CD_IMG, "common_icon": Const.COMMON_IMG,
        "close_icon": Const.CLOSE_IMG,
    },
    "Settings": {"monitor_hand_s": "300", "lang": "RUS"},
    "Bots": {"discord_webhook": "", "tg_token": "", "tg_chat_id": "",
             "ds_mention_id": "", "tg_mention_user": ""},
    "Spinning": {"jig_reel_time": "1.42", "jig_pause_time": "2.58",
                 "jig_mode": "0", "casting_rod": "0"},
    "Modules": {"disable_ctrl": "1", "chat_messages": "1", "auto_rods": "1"},
}


def load_config() -> configparser.ConfigParser:
    """Read existing values; add missing defaults without writing on import."""
    loaded = configparser.ConfigParser()
    loaded.read_dict(DEFAULTS)
    loaded.read(Const.CFG_FILE, encoding="utf-8")
    return loaded


def load_langs() -> dict:
    try:
        with open(resource_path("lang.json"), encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {language: {} for language in ("UKR", "RUS", "ENG", "CHN", "GER", "POL")}


def resolve_tesseract(configured: str) -> str:
    """Use the saved executable, a local copy, or the one available on PATH."""
    candidates = [configured, data_path("tesseract/tesseract.exe"), shutil.which("tesseract")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return configured


config = load_config()
LANGS = load_langs()
game_title = config.get("Paths", "game_title")
FISH_IMG = resource_path(config.get("Images", "fish_icon"))
DONE_IMG = resource_path(config.get("Images", "done_icon"))
DANGER_IMG = resource_path(config.get("Images", "danger_icon"))
LOCK_ICON = resource_path(config.get("Images", "lock_icon"))
TROPHY_IMG = resource_path(config.get("Images", "trophy_icon"))
TROPHY2_IMG = resource_path(config.get("Images", "trophy2_icon"))
CARD_IMG = resource_path(config.get("Images", "card_icon"))
COMMON_IMG = resource_path(config.get("Images", "common_icon"))
CLOSE_IMG = resource_path(config.get("Images", "close_icon"))
