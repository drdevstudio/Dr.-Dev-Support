"""
firebase_helper.py — thin REST client for Firebase Realtime Database.
Also provides log_event() which appends to /logs so that (per project
requirement) every meaningful action is recorded permanently.
"""
import datetime
import time
import requests
import config

TIMEOUT = 12


def _firebase_url() -> str:
    return config.FIREBASE_URL.rstrip("/")


def _secret() -> str:
    return config.FIREBASE_SECRET


def _url(path: str) -> str:
    base = f"{_firebase_url()}/{path}.json"
    s = _secret()
    return f"{base}?auth={s}" if s else base


def _enabled() -> bool:
    return bool(_firebase_url())


def get(path: str):
    if not _enabled():
        return None
    try:
        r = requests.get(_url(path), timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[FB GET] {path} -> {e}")
        return None


def put(path: str, data):
    if not _enabled():
        return None
    try:
        r = requests.put(_url(path), json=data, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[FB PUT] {path} -> {e}")
        return None


def patch(path: str, data: dict):
    if not _enabled():
        return None
    try:
        r = requests.patch(_url(path), json=data, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[FB PATCH] {path} -> {e}")
        return None


def post(path: str, data):
    if not _enabled():
        return None
    try:
        r = requests.post(_url(path), json=data, timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[FB POST] {path} -> {e}")
        return None


def delete(path: str) -> bool:
    """Hard delete. Intentionally NOT used for chat messages — see
    soft_delete_message() in telegram_bot.py. Kept for admin/log housekeeping
    only (e.g. clearing rate-limit counters, never for message history)."""
    if not _enabled():
        return False
    try:
        r = requests.delete(_url(path), timeout=TIMEOUT)
        return r.status_code == 200
    except Exception as e:
        print(f"[FB DEL] {path} -> {e}")
        return False


def get_list(path: str) -> list:
    data = get(path)
    if not data or not isinstance(data, dict):
        return []
    return [{"_id": k, **v} if isinstance(v, dict) else {"_id": k, "value": v} for k, v in data.items()]


# ── Activity log ──────────────────────────────────────────────────────────────
def log_event(event_type: str, **fields):
    """Append-only activity log at /logs/{ts_id}. Never overwritten or
    deleted automatically. Use for every meaningful action:
    message_in, message_out, admin_login, admin_login_failed, blocked,
    unblocked, message_deleted, spam_detected, bot_error, etc.
    """
    try:
        entry = {
            "type": event_type,
            "time": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "ts": int(time.time()),
            **fields,
        }
        post("logs", entry)
    except Exception as e:
        print(f"[LOG] {event_type} -> {e}")
