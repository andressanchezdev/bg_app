"""Inicio automático con Windows (HKCU\\...\\Run) para la aplicación instalada."""
import sys

import app_paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "RemoverBackgroundIP"
LEGACY_VALUE_NAMES = ("IABackgroundRemover",)
BACKGROUND_FLAG = "--background"


def is_supported() -> bool:
    return sys.platform == "win32" and app_paths.is_frozen()


def command() -> str:
    return f'"{sys.executable}" {BACKGROUND_FLAG}'


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not is_supported():
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        for legacy in LEGACY_VALUE_NAMES:
            try:
                winreg.DeleteValue(key, legacy)
            except FileNotFoundError:
                pass
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
