# keep_alive.py
import os
import time
import requests
from threading import Thread

def ping_self():
    url = os.getenv("RENDER_URL")
    token = os.getenv("TOKEN")  # 直接用 webhook 的完整 path
    if not url or not token:
        print("[KeepAlive] RENDER_URL or TOKEN not set, skipping ping")
        return

    ping_url = f"{url}/{token}"
    print(f"[KeepAlive] Pinging {ping_url} every 10 minutes...")

    while True:
        try:
            requests.get(ping_url, timeout=10)
            print(f"[KeepAlive] Pinged {ping_url}")
        except Exception as e:
            print(f"[KeepAlive] Ping failed: {e}")
        time.sleep(600)  # 每 10 分鐘 ping 一次

def keep_alive():
    thread = Thread(target=ping_self, daemon=True)
    thread.start()
