"""
app.py — Support Bot Admin Panel (Flask)

Routes:
  GET/POST /login, /logout
  GET      /                         -> chat list (dashboard)
  GET      /chat/<cid>               -> WhatsApp-style single chat view
  POST     /chat/<cid>/send          -> admin sends text
  POST     /chat/<cid>/send_file     -> admin sends a file (uploaded from browser)
  GET      /chat/<cid>/file/<mid>/download -> proxies the file from Telegram
  POST     /chat/<cid>/message/<mid>/edit
  POST     /chat/<cid>/message/<mid>/delete   (soft delete, see telegram_bot.py)
  POST     /chat/<cid>/block , /unblock
  GET      /chat/<cid>/messages      -> JSON, used for polling
  GET      /unread_count             -> JSON, used for the sidebar badge
  GET      /logs                     -> raw activity log viewer
  GET      /health , /ping           -> for UptimeRobot / Render health checks
"""
import io
import secrets
import threading
import time
from functools import wraps

import requests
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for, flash

import config
import firebase_helper as fb
import telegram_bot as tg

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

# ── login brute-force guard (per-IP, in-memory) ──────────────────────────────
_login_attempts = {}
_lock = threading.Lock()


def _login_locked(ip: str) -> int:
    with _lock:
        rec = _login_attempts.get(ip)
        if not rec:
            return 0
        count, first_ts, locked_until = rec
        remaining = locked_until - time.time()
        return max(0, int(remaining))


def _record_failed_login(ip: str):
    with _lock:
        count, first_ts, _ = _login_attempts.get(ip, (0, time.time(), 0))
        count += 1
        locked_until = 0
        if count >= config.LOGIN_MAX_ATTEMPTS:
            locked_until = time.time() + config.LOGIN_LOCKOUT_SECONDS
        _login_attempts[ip] = (count, first_ts, locked_until)


def _clear_failed_login(ip: str):
    with _lock:
        _login_attempts.pop(ip, None)


def login_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return decorated


@app.context_processor
def inject_globals():
    return {"panel_name": config.PANEL_NAME}


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
        locked_for = _login_locked(ip)
        if locked_for:
            flash(f"Too many failed attempts. Try again in {locked_for}s.", "danger")
            return render_template("login.html")

        entered_user = request.form.get("username", "").strip()
        entered_pass = request.form.get("password", "").strip()

        user_ok = secrets.compare_digest(entered_user, config.ADMIN_USERNAME)
        pass_ok = secrets.compare_digest(entered_pass, config.ADMIN_PASSWORD)

        if user_ok and pass_ok:
            session["admin"] = True
            session.permanent = True
            _clear_failed_login(ip)
            fb.log_event("admin_login", ip=ip)
            return redirect(url_for("chats"))

        _record_failed_login(ip)
        fb.log_event("admin_login_failed", ip=ip, username=entered_user)
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Chat list (dashboard) ─────────────────────────────────────────────────────
@app.route("/")
@login_required
def chats():
    raw = fb.get("support") or {}
    items = []
    for cid, data in raw.items():
        meta = (data or {}).get("meta", {})
        if not meta:
            continue
        meta = {**meta, "chat_id": cid}
        items.append(meta)
    items.sort(key=lambda c: c.get("last_ts", 0), reverse=True)
    total_unread = sum(c.get("unread", 0) for c in items)
    return render_template("chats.html", chats=items, total_unread=total_unread)


def _get_messages(cid):
    raw = fb.get(f"support/{cid}/messages") or {}
    return sorted(raw.values(), key=lambda m: m.get("ts", 0))


def _get_meta(cid):
    return fb.get(f"support/{cid}/meta") or {}


@app.route("/chat/<cid>")
@login_required
def chat_view(cid):
    meta = _get_meta(cid)
    msgs_raw = fb.get(f"support/{cid}/messages") or {}
    for mid, m in msgs_raw.items():
        if m.get("from") == "user" and not m.get("read"):
            fb.patch(f"support/{cid}/messages/{mid}", {"read": True})
    fb.patch(f"support/{cid}/meta", {"unread": 0})
    messages = sorted(msgs_raw.values(), key=lambda m: m.get("ts", 0))
    return render_template("chat.html", cid=cid, meta=meta, messages=messages)


@app.route("/chat/<cid>/send", methods=["POST"])
@login_required
def chat_send(cid):
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty message"})
    return jsonify(tg.admin_reply(cid, text))


@app.route("/chat/<cid>/send_file", methods=["POST"])
@login_required
def chat_send_file(cid):
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file provided"}), 400
    caption = request.form.get("text", "").strip()
    file_bytes = f.read()
    if len(file_bytes) > config.MAX_UPLOAD_MB * 1024 * 1024:
        return jsonify({"error": f"File exceeds {config.MAX_UPLOAD_MB}MB limit"}), 413
    filename = f.filename or "file"
    mime_type = f.content_type or "application/octet-stream"
    return jsonify(tg.admin_send_file(cid, file_bytes, filename, mime_type, caption))


@app.route("/chat/<cid>/file/<mid>/download")
@login_required
def chat_file_download(cid, mid):
    """Streams the file through our server (rather than 302-redirecting to a
    possibly-stale cached URL) by resolving a fresh URL from file_id every
    time. Forces a Content-Disposition so 'download from admin panel' works
    for every file type, including ones browsers would otherwise preview."""
    msgs = fb.get(f"support/{cid}/messages") or {}
    m = msgs.get(mid)
    if not m:
        return "Not found", 404
    file_id = m.get("file_id")
    url = tg.refresh_file_url(file_id) if file_id else (m.get("file_url") or "")
    if not url:
        return "File unavailable", 404
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.status_code != 200:
            return "File unavailable on Telegram's servers", 404
        filename = m.get("file_name") or f"{mid}"
        return Response(
            r.iter_content(chunk_size=65536),
            mimetype=r.headers.get("Content-Type", "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return f"Download error: {e}", 500


@app.route("/chat/<cid>/messages")
@login_required
def chat_messages_json(cid):
    return jsonify(_get_messages(cid))


@app.route("/chat/<cid>/message/<mid>/edit", methods=["POST"])
@login_required
def chat_edit(cid, mid):
    if not mid.startswith("admin_"):
        return jsonify({"error": "Only admin messages can be edited"}), 400
    new_text = request.form.get("text", "").strip()
    if not new_text:
        return jsonify({"error": "Empty"})
    return jsonify(tg.admin_edit_message(cid, mid, new_text))


@app.route("/chat/<cid>/message/<mid>/delete", methods=["POST"])
@login_required
def chat_delete(cid, mid):
    # Soft delete only — see telegram_bot.soft_delete_message(). Nothing is
    # ever hard-removed from Firebase.
    return jsonify(tg.soft_delete_message(cid, mid, deleted_by="admin"))


@app.route("/chat/<cid>/block", methods=["POST"])
@login_required
def chat_block(cid):
    return jsonify(tg.block_user(cid))


@app.route("/chat/<cid>/unblock", methods=["POST"])
@login_required
def chat_unblock(cid):
    return jsonify(tg.unblock_user(cid))


@app.route("/unread_count")
@login_required
def unread_count():
    raw = fb.get("support") or {}
    total = sum((v.get("meta", {}) or {}).get("unread", 0) for v in raw.values() if isinstance(v, dict))
    return jsonify({"count": total})


# ── Activity log viewer ───────────────────────────────────────────────────────
@app.route("/logs")
@login_required
def logs_view():
    raw = fb.get("logs") or {}
    items = sorted(raw.values(), key=lambda e: e.get("ts", 0), reverse=True)[:300]
    return render_template("logs.html", logs=items)


# ── Health checks (UptimeRobot / Render) ─────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "bot": bool(tg.bot)})


@app.route("/ping")
def ping():
    return "pong", 200


# ── Bot startup ───────────────────────────────────────────────────────────────
_bot_thread_started = False
_bot_lock = threading.Lock()


def _start_bot_once():
    global _bot_thread_started
    with _bot_lock:
        if _bot_thread_started:
            return
        if not tg.bot:
            print("BOT_TOKEN not set — support bot will not start.")
            return
        threading.Thread(target=tg.run_bot, daemon=True).start()
        _bot_thread_started = True
        print("Support bot thread started.")


_start_bot_once()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
