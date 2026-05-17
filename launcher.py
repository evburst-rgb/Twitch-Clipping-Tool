import json
import os
import sys
import threading
import time
import webbrowser
import winreg
from pathlib import Path
from tkinter import Tk, simpledialog, messagebox

import pystray
import requests
from PIL import Image
from pynput import keyboard

APP_NAME = "EvBurst Clipping Tool"
APP_URL = "https://twitch-clipping-tool.onrender.com"
ICON_FILE = "evburst_clipping_tool.ico"

DEFAULT_HOTKEY = "F10"

HOTKEY_MAP = {
    "F8": keyboard.Key.f8,
    "F9": keyboard.Key.f9,
    "F10": keyboard.Key.f10,
}


def get_app_data_dir():
    app_data = os.getenv("APPDATA")
    folder = Path(app_data) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


CONFIG_FILE = get_app_data_dir() / "config.json"


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def load_config():
    if not CONFIG_FILE.exists():
        return {
            "trigger_url": "",
            "hotkey": DEFAULT_HOTKEY
        }

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            config = json.load(file)

        config.setdefault("trigger_url", "")
        config.setdefault("hotkey", DEFAULT_HOTKEY)

        return config
    except Exception:
        return {
            "trigger_url": "",
            "hotkey": DEFAULT_HOTKEY
        }


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)


def get_trigger_url():
    return load_config().get("trigger_url", "").strip()


def get_hotkey():
    hotkey = load_config().get("hotkey", DEFAULT_HOTKEY).strip().upper()

    if hotkey not in HOTKEY_MAP:
        return DEFAULT_HOTKEY

    return hotkey


def set_trigger_url(icon=None, item=None):
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    current_url = get_trigger_url()

    new_url = simpledialog.askstring(
        "EvBurst Clipping Tool",
        "Paste your Stream Deck Trigger URL:",
        initialvalue=current_url
    )

    if new_url:
        config = load_config()
        config["trigger_url"] = new_url.strip()
        save_config(config)

        sync_config_from_server()

        messagebox.showinfo(
            "EvBurst Clipping Tool",
            "Trigger URL saved successfully."
        )

    root.destroy()


def sync_config_from_server():
    trigger_url = get_trigger_url()

    if not trigger_url:
        return

    try:
        streamdeck_key = trigger_url.rstrip("/").split("/")[-1]
        api_url = f"{APP_URL}/api/user-config/{streamdeck_key}"

        response = requests.get(api_url, timeout=15)

        if response.status_code != 200:
            return

        data = response.json()

        hotkey = data.get("hotkey", DEFAULT_HOTKEY).strip().upper()

        if hotkey not in HOTKEY_MAP:
            hotkey = DEFAULT_HOTKEY

        config = load_config()
        config["trigger_url"] = data.get("trigger_url", trigger_url)
        config["hotkey"] = hotkey
        save_config(config)

    except Exception:
        pass


def background_sync_loop():
    while True:
        sync_config_from_server()
        time.sleep(60)


def open_dashboard(icon=None, item=None):
    webbrowser.open(APP_URL)


def trigger_clip(icon=None, item=None):
    trigger_url = get_trigger_url()

    if not trigger_url:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        messagebox.showwarning(
            "EvBurst Clipping Tool",
            "No Trigger URL saved yet.\n\nRight-click the tray icon and choose Set Trigger URL."
        )

        root.destroy()
        return

    def run_request():
        try:
            requests.get(trigger_url, timeout=25)
        except Exception:
            pass

    threading.Thread(target=run_request, daemon=True).start()


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


def start_hotkey_listener():
    pressed_keys = set()

    def on_press(key):
        pressed_keys.add(key)

        current_hotkey = get_hotkey()
        target_key = HOTKEY_MAP.get(current_hotkey, keyboard.Key.f10)

        if key == target_key:
            trigger_clip()

    def on_release(key):
        pressed_keys.discard(key)

    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    )

    listener.daemon = True
    listener.start()


def quit_app(icon=None, item=None):
    icon.stop()


def main():
    sync_config_from_server()

    threading.Thread(target=background_sync_loop, daemon=True).start()

    start_hotkey_listener()

    icon_path = resource_path(ICON_FILE)
    image = Image.open(icon_path)

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
        pystray.MenuItem("Set Trigger URL", set_trigger_url),
        pystray.MenuItem(lambda item: f"Trigger Clip Now ({get_hotkey()})", trigger_clip),
        pystray.Menu.SEPARATOR,
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