import json
import os
import re
import sys
import threading
import time
import webbrowser
import winreg
import yt_dlp
from datetime import datetime
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


def get_default_clip_folder():
    videos_folder = Path.home() / "Videos"
    clip_folder = videos_folder / "Stream Clips"
    clip_folder.mkdir(parents=True, exist_ok=True)
    return clip_folder


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


def get_streamdeck_key():
    trigger_url = get_trigger_url()

    if not trigger_url:
        return ""

    return trigger_url.rstrip("/").split("/")[-1]


def mark_clip_downloaded(clip_id):
    if not clip_id:
        return

    config = load_config()
    downloaded = set(config.get("downloaded_clip_ids", []))
    downloaded.add(clip_id)

    config["downloaded_clip_ids"] = list(downloaded)[-100:]
    save_config(config)


def get_downloaded_clip_ids():
    config = load_config()
    return set(config.get("downloaded_clip_ids", []))


def get_hotkey():
    hotkey = load_config().get("hotkey", DEFAULT_HOTKEY).strip().upper()

    if hotkey not in HOTKEY_MAP:
        return DEFAULT_HOTKEY

    return hotkey


def safe_filename(text):
    if not text:
        return "Stream_Clip"

    cleaned = re.sub(r'[<>:"/\\|?*]', "", text)
    cleaned = cleaned.strip()

    if not cleaned:
        return "Stream_Clip"

    return cleaned[:80]


def derive_mp4_url(thumbnail_url):
    if not thumbnail_url:
        return None

    if "/thumb/" in thumbnail_url:
        return thumbnail_url.replace(
            "/landscape/thumb/thumb-0000000000-480x272.jpg",
            "/720p60.mp4"
        )

    if "-preview-" in thumbnail_url:
        base_url = thumbnail_url.split("-preview-")[0]
        return f"{base_url}.mp4"

    return None


def sync_config_from_server():
    streamdeck_key = get_streamdeck_key()

    if not streamdeck_key:
        return

    try:
        api_url = f"{APP_URL}/api/user-config/{streamdeck_key}"
        response = requests.get(api_url, timeout=15)

        if response.status_code != 200:
            return

        data = response.json()
        hotkey = data.get("hotkey", DEFAULT_HOTKEY).strip().upper()

        if hotkey not in HOTKEY_MAP:
            hotkey = DEFAULT_HOTKEY

        config = load_config()
        config["trigger_url"] = data.get("trigger_url", get_trigger_url())
        config["hotkey"] = hotkey
        save_config(config)

    except Exception:
        pass


def background_sync_loop():
    while True:
        sync_config_from_server()
        time.sleep(60)


def background_clip_download_loop():
    while True:

        print("Checking for new clips...")

        try:
            download_latest_clip()
        except Exception:
            pass

        time.sleep(20)


def set_trigger_url(icon=None, item=None):

    def show_prompt():

        root = Tk()
        root.withdraw()

        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()

        current_url = get_trigger_url()

        new_url = simpledialog.askstring(
            "EvBurst Clipping Tool",
            "Paste your Stream Deck Trigger URL:",
            initialvalue=current_url,
            parent=root
        )

        if new_url:
            config = load_config()
            config["trigger_url"] = new_url.strip()
            save_config(config)

            sync_config_from_server()

            messagebox.showinfo(
                "EvBurst Clipping Tool",
                "Trigger URL saved successfully.",
                parent=root
            )

        root.destroy()

    threading.Thread(target=show_prompt, daemon=True).start()


def open_dashboard(icon=None, item=None):
    webbrowser.open(APP_URL)


def open_clip_folder(icon=None, item=None):
    folder = get_default_clip_folder()
    os.startfile(folder)


def get_latest_clip():
    streamdeck_key = get_streamdeck_key()

    if not streamdeck_key:
        return None

    try:
        api_url = f"{APP_URL}/api/latest-clip/{streamdeck_key}"
        response = requests.get(api_url, timeout=20)

        if response.status_code != 200:
            return None

        return response.json()

    except Exception:
        return None


def download_latest_clip():
    clip = get_latest_clip()

    if not clip:
        print("No latest clip found.")
        return False

    clip_id = clip.get("clip_id")

    print("Latest clip ID:", clip_id)

    if clip_id in get_downloaded_clip_ids():
        return False

    clip_url = clip.get("clip_url")

    if not clip_url:
        print("No clip URL found.")
        return False

    clip_title = clip.get("clip_title") or "Stream Clip"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    filename = f"{timestamp}_{safe_filename(clip_title)}.mp4"
    save_path = get_default_clip_folder() / filename

    try:
        ydl_opts = {
            "outtmpl": str(save_path),
            "format": "mp4/best",
            "quiet": False,
            "noplaylist": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([clip_url])

        print("Downloaded clip to:", save_path)
        mark_clip_downloaded(clip_id)

        return True

    except Exception as e:
        print("Download failed:", e)
        return False
    

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

    def run_clip_workflow():
        try:
            requests.get(trigger_url, timeout=35)
        except Exception:
            return

        time.sleep(8)

        download_latest_clip()

    threading.Thread(target=run_clip_workflow, daemon=True).start()


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
    def on_press(key):
        current_hotkey = get_hotkey()
        target_key = HOTKEY_MAP.get(current_hotkey, keyboard.Key.f10)

        if key == target_key:
            trigger_clip()

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()


def quit_app(icon=None, item=None):
    icon.stop()


def main():
    sync_config_from_server()

    webbrowser.open(APP_URL)

    threading.Thread(target=background_sync_loop, daemon=True).start()
    threading.Thread(target=background_clip_download_loop, daemon=True).start()

    start_hotkey_listener()

    icon_path = resource_path(ICON_FILE)
    image = Image.open(icon_path)

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
        pystray.MenuItem("Set Trigger URL", set_trigger_url),
        pystray.MenuItem(lambda item: f"Trigger Clip Now ({get_hotkey()})", trigger_clip),
        pystray.MenuItem("Open Clip Folder", open_clip_folder),
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