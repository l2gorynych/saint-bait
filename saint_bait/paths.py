"""Stable paths for source runs and PyInstaller builds."""

from pathlib import Path
import sys

APP_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
           else Path(__file__).resolve().parent.parent)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))


def data_path(relative_path: str) -> str:
    """Settings, logs and generated files live beside the application."""
    return str(APP_DIR / relative_path)


def resource_path(relative_path: str) -> str:
    """Resolve bundled assets independently of the shell working directory."""
    path = Path(relative_path)
    if path.is_absolute():
        return str(path)
    bundled = BUNDLE_DIR / path
    return str(bundled if bundled.exists() else APP_DIR / path)
