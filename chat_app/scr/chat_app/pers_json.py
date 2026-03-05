
import json
import os
from datetime import datetime

HISTORY_FILE = "chat_history.json"


def _load_file() -> dict:

    if not os.path.exists(HISTORY_FILE):
        return {}

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}  


def _save_file(data: dict) -> None:

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_rooms() -> list[str]:

    return list(_load_file().keys())


def save_message(room: str, username: str, text: str) -> None:

    data = _load_file()
    room = room.strip().upper()

    if room not in data:
        data[room] = []

    data[room].append({
        "timestamp" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "username"  : username.strip().title(),
        "text"      : text.strip()
    })

    _save_file(data)


def load_history(room: str) -> list[dict]:

    data = _load_file()
    return data.get(room.strip().upper(), [])