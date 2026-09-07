"""
config.py — all configuration comes from environment variables.
Nothing here is stored in Firebase; Firebase is used only as the message/log store.
"""
import os


def _clean(v: str) -> str:
    return (v or "").strip()


# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN = _clean(os.environ.get("BOT_TOKEN", ""))


def ADMIN_CHAT_IDS() -> list:
    """One or more admin Telegram chat IDs (comma separated) that get notified
    and are allowed to use the /reply, /block etc. bot-side shortcuts."""
    raw = _clean(os.environ.get("ADMIN_CHAT_ID", ""))
    return [x.strip() for x in raw.split(",") if x.strip()]


# ── Firebase Realtime Database ───────────────────────────────────────────────
FIREBASE_URL = _clean(os.environ.get("FIREBASE_URL", ""))
FIREBASE_SECRET = _clean(os.environ.get("FIREBASE_SECRET", ""))

# ── Admin panel auth ──────────────────────────────────────────────────────────
ADMIN_USERNAME = _clean(os.environ.get("ADMIN_USERNAME", "admin"))
ADMIN_PASSWORD = _clean(os.environ.get("ADMIN_PASSWORD", "admin123"))

# ── Flask ─────────────────────────────────────────────────────────────────────
SECRET_KEY = _clean(os.environ.get("SECRET_KEY", "")) or os.urandom(24).hex()
PORT = int(os.environ.get("PORT", 5000))
PANEL_NAME = _clean(os.environ.get("PANEL_NAME", "Support Panel"))

# Public base URL of this deployed service (used to build "open panel" links
# in admin notifications). e.g. https://my-support-bot.onrender.com
PANEL_URL = _clean(os.environ.get("PANEL_URL", ""))

# ── Greetings / auto replies (optional) ──────────────────────────────────────
WELCOME_MESSAGE = os.environ.get(
    "WELCOME_MESSAGE",
    "👋 *Welcome to Support!*\n"
    "Please describe your issue and we'll get back to you shortly.\n\n"
    "📸 You can also send photos, videos or files.",
)
AUTO_REPLY = os.environ.get(
    "AUTO_REPLY",
    "✅ Message received! Admin will answer you soon.",
)
# How often the auto-reply is allowed to fire per user, in minutes. This
# stops it from being sent after every single message (which would be
# spammy) — it behaves like a WhatsApp Business "away message": once,
# then again only after this many minutes of the conversation being quiet.
# Set to 0 to send it after every message instead.
AUTO_REPLY_COOLDOWN_MINUTES = int(os.environ.get("AUTO_REPLY_COOLDOWN_MINUTES", 30))

# ── Anti-spam tuning (all optional, sane defaults) ───────────────────────────
ANTI_SPAM_MAX_MSGS = int(os.environ.get("ANTI_SPAM_MAX_MSGS", 6))       # msgs
ANTI_SPAM_WINDOW_SECONDS = int(os.environ.get("ANTI_SPAM_WINDOW_SECONDS", 10))  # per N seconds
ANTI_SPAM_MIN_GAP_SECONDS = float(os.environ.get("ANTI_SPAM_MIN_GAP_SECONDS", 0.6))  # min gap between msgs
ANTI_SPAM_DUPLICATE_LIMIT = int(os.environ.get("ANTI_SPAM_DUPLICATE_LIMIT", 3))  # identical msgs in a row
ANTI_SPAM_MUTE_SECONDS = int(os.environ.get("ANTI_SPAM_MUTE_SECONDS", 60))       # temp mute duration
ANTI_SPAM_MAX_STRIKES = int(os.environ.get("ANTI_SPAM_MAX_STRIKES", 4))  # strikes before auto-block

# ── Login brute-force protection ─────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", 5))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", 300))

# ── Uploads ───────────────────────────────────────────────────────────────────
# Telegram Bot API hard limits: ~20MB download via getFile, up to 50MB upload
# for documents/video sent by a bot. Keep some headroom below that.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 45))
