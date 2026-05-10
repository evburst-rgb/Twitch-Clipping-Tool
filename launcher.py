import os
import sys
import webbrowser
import winreg
from pathlib import Path

import pystray
from PIL import Image

APP_NAME = "EvBurst Clipping Tool"
APP_URL = "https://twitch-clipping-tool.onrender.com"
ICON_FILE = "evburst_clipping_tool.ico"


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def open_dashboard(icon=None, item=None):
    webbrowser.open(APP_URL)


def get_exe_path():
    return sys.executable


def enable_startup():
    exe_path = get_exe_path()

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE
    )

    winreg.SetValueEx(
        key,
        APP_NAME,
        0,
        winreg.REG_SZ,
        f'"{exe_path}"'
    )

    winreg.CloseKey(key)


def disable_startup():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )

        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


def is_startup_enabled():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )

        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)

        return value.strip('"') == get_exe_path()

    except FileNotFoundError:
        return False


def toggle_startup(icon=None, item=None):
    if is_startup_enabled():
        disable_startup()
    else:
        enable_startup()

    icon.update_menu()


def quit_app(icon=None, item=None):
    icon.stop()


def main():
    icon_path = resource_path(ICON_FILE)
    image = Image.open(icon_path)

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
        pystray.MenuItem(
            "Run at Windows Startup",
            toggle_startup,
            checked=lambda item: is_startup_enabled()
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app)
    )

    tray_icon = pystray.Icon(
        APP_NAME,
        image,
        APP_NAME,
        menu
    )

    tray_icon.run()


if __name__ == "__main__":
    main()