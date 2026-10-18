"""Session log output."""

import time
import threading

from .paths import data_path

_write_lock = threading.Lock()


def log(m, ui_ref=None):
    ts = time.strftime('%H:%M:%S')
    clean = m.translate({ord(c): None for c in '🎣🏆🕸️🔄❌⚠️👤🚀✅⬇️🔓'})
    full_msg = f'[{ts}] {clean}'
    if ui_ref:
        ui_ref.update_log(full_msg)
        if hasattr(ui_ref, 'check_log_to_file') and ui_ref.check_log_to_file.get():
            try:
                with _write_lock, open(data_path('podust.log'), 'a', encoding='utf-8') as f:
                    f.write(full_msg + '\n')
            except Exception:
                pass
