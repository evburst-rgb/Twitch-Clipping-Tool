import requests

try:
    requests.get("http://127.0.0.1:8765/clip", timeout=5)
except Exception:
    pass