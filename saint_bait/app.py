"""Desktop entry point. Opening the app never starts fishing."""

import os
import signal
import sys

from .paths import APP_DIR


def main() -> None:
    if len(sys.argv)==3 and sys.argv[1]=='--install-update':
        from .updates import install_staged
        install_staged(sys.argv[2])
        return
    # Legacy capture routines use relative output names. Keep those routines
    # unchanged while making launches from another folder reliable.
    os.chdir(APP_DIR)
    from .ui import SaintBaitUI

    app = SaintBaitUI()

    def shutdown(_signum, _frame):
        app.on_closing()

    signal.signal(signal.SIGINT, shutdown)
    app.mainloop()
