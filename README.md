# Support Bot — Standalone Telegram Customer Support System

A self-contained customer-support system, separate from your shop project:
users message your Telegram bot, admin replies from a WhatsApp-style web
panel (login-protected), files can be exchanged both ways, everything is
logged to Firebase Realtime Database, and it's built to run on Render's
free tier kept alive by UptimeRobot.

## What's included

| File | Purpose |
|---|---|
| `app.py` | Flask admin panel (login, chat list, chat view, uploads, logs) |
| `telegram_bot.py` | The bot: receives user messages, notifies admin, soft-delete, block/unblock |
| `antispam.py` | In-memory flood/duplicate-message protection |
| `firebase_helper.py` | Firebase REST client + append-only activity logger |
| `config.py` | All settings, read from environment variables only |
| `templates/` | `login.html`, `chats.html` (user list), `chat.html` (WhatsApp-style chat), `logs.html` |

## How it behaves (per your spec)

- **Nothing is ever hard-deleted.** Clicking delete in the admin panel sets
  `deleted: true` on that message in Firebase; the chat then shows a
  "🚫 This message was deleted" placeholder (WhatsApp Business style), but
  the row and its original content stay in the database permanently.
  **Limitation that's on Telegram's side, not this code:** Telegram's Bot
  API has no event for "a user deleted their own message" in a private
  chat — there's no such webhook for anyone building bots. What's
  implemented is the part that's actually possible: your own deletions
  from the panel are soft, and the bot's own sent messages are
  best-effort removed from the Telegram side too.
- **Admin panel:** username/password login (from env vars, brute-force
  locked after `LOGIN_MAX_ATTEMPTS` failures), a WhatsApp-style user list,
  click a user to see the full thread.
- **Files:** users can send photos/videos/documents; the admin can too.
  Every download link in the panel re-resolves a fresh Telegram file URL
  server-side (instead of trusting a cached link that can go stale) and
  forces a real download.
- **Firebase logging:** every message in/out, login, login failure,
  block/unblock, delete, and spam event is appended to `/logs` — view it
  at `/logs` in the panel.
- **Admin notifications:** every new user message pings all chat IDs in
  `ADMIN_CHAT_ID` with a preview and a link into the panel.
- **Auto-reply to the user:** by default, the first message in a
  conversation (and again after `AUTO_REPLY_COOLDOWN_MINUTES`, default 30,
  of quiet) gets an automatic "✅ Message received! Admin will answer you
  soon." reply — for text *and* for photos/videos/files. This is a
  WhatsApp Business-style away-message, not a reply to every single
  message (that would get spammy fast). Customize the text with
  `AUTO_REPLY`, or set `AUTO_REPLY=""` to disable it entirely, or
  `AUTO_REPLY_COOLDOWN_MINUTES=0` to send it after every message instead.
- **Anti-spam:** per-chat rate limiting (max messages per time window),
  minimum gap between messages, repeated-identical-message detection,
  temporary mute, and auto-block after repeated strikes — all tunable via
  env vars, see `.env.example`.

## 1. Get your credentials

- **Bot token:** talk to [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`.
- **Your admin chat ID:** message [@userinfobot](https://t.me/userinfobot) — it replies with your numeric ID.
- **Firebase Realtime Database:**
  1. [console.firebase.google.com](https://console.firebase.google.com) → Create project → Build → Realtime Database → Create Database.
  2. Copy the database URL (`https://xxxx-default-rtdb.firebaseio.com`) → `FIREBASE_URL`.
  3. Project settings (⚙️) → Service accounts → **Database secrets** → copy the secret → `FIREBASE_SECRET`.
     (This is Firebase's legacy secret, simplest for a small REST-only bot like this — no service-account JSON needed.)
  4. Rules can stay locked down (`{"rules": {".read": false, ".write": false}}`) since every request from this app is authenticated with `?auth=<secret>`, which bypasses those rules.

## 2. Run locally (optional, to test before deploying)

```bash
git clone <your-repo-url> support-bot
cd support-bot
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in BOT_TOKEN, ADMIN_CHAT_ID, FIREBASE_URL, FIREBASE_SECRET,
# ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY

# load .env and run (add `from dotenv import load_dotenv; load_dotenv()`
# at the very top of app.py first, or just export the vars manually)
export $(grep -v '^#' .env | xargs)   # macOS/Linux
python3 app.py
```

Visit `http://localhost:5000`, log in, and message your bot on Telegram to
see it appear in the panel.

## 3. Deploy to Render (free web service)

**Option A — one-click via Blueprint (`render.yaml` is already included):**

```bash
git init
git add .
git commit -m "Initial commit: standalone support bot"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

Then in Render:
1. New → **Blueprint** → connect the repo → Render reads `render.yaml` automatically.
2. It creates one free web service. Fill in the env vars it prompts for
   (`BOT_TOKEN`, `ADMIN_CHAT_ID`, `FIREBASE_URL`, `FIREBASE_SECRET`,
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `PANEL_URL`) in the Render dashboard
   — `SECRET_KEY` is auto-generated for you.
3. Deploy. Once live, copy the service URL (`https://xxxx.onrender.com`)
   into the `PANEL_URL` env var and redeploy so admin notifications get a
   working "Open in Admin Panel" button.

**Option B — manual, no Blueprint:**

1. New → **Web Service** → connect your repo.
2. Runtime: **Python 3**. Build command:
   ```
   pip install -r requirements.txt
   ```
3. Start command:
   ```
   gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
   ```
   **`--workers 1` is not optional.** The bot's `getUpdates` long-polling
   runs in a background thread inside the web process. If Render (or you)
   spins up more than one worker/process, you get two pollers fighting
   over the same bot token and Telegram returns
   `409 Conflict: terminated by other getUpdates request`, causing
   messages to randomly stop arriving. One worker + threads for concurrent
   HTTP requests is the correct setup for this architecture.
4. Instance type: **Free**.
5. Add the environment variables listed in `.env.example` under
   Environment → Add Environment Variable (do this for every one of
   `BOT_TOKEN`, `ADMIN_CHAT_ID`, `FIREBASE_URL`, `FIREBASE_SECRET`,
   `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY`, `PANEL_URL`).
6. Deploy. Health check path (if asked): `/health`.

## 4. Keep it awake with UptimeRobot

Render's free web services sleep after ~15 minutes without incoming HTTP
traffic. A ping keeps the process (and the bot's polling thread inside it)
alive.

1. [uptimerobot.com](https://uptimerobot.com) → sign up (free) → **Add New Monitor**.
2. Monitor Type: **HTTP(s)**.
3. URL: `https://<your-service>.onrender.com/ping`
4. Monitoring interval: **5 minutes**.
5. Save.

That's it — as long as UptimeRobot keeps hitting `/ping` every 5 minutes,
the service (and your bot) stays up 24/7 on the free tier.

## 5. First login

Go to `https://<your-service>.onrender.com/login` and sign in with the
`ADMIN_USERNAME` / `ADMIN_PASSWORD` you set. Message your bot on Telegram
from a second account/phone — it should show up in the chat list within
a few seconds, and you'll get an admin notification.

## Notes & honest limitations

- **Free Render + long polling** means a brief gap (a few seconds, not
  minutes) after a cold start before the bot picks up the very first
  message post-wake — normal for any polling bot on a free tier; the
  UptimeRobot ping minimizes how often this happens.
- **File size:** Telegram bots can download files up to ~20MB via the API
  used for the panel's download links; sending documents as the bot
  supports up to ~50MB. `MAX_UPLOAD_MB` (default 45) keeps you inside
  Telegram's own ceiling — raising it much further will just fail on
  Telegram's side, not this app's.
- **Message-deletion detection**, as noted above, cannot reflect a user
  deleting their own message on their device — no Telegram Bot API event
  exists for that in private chats. Everything else (soft-delete from the
  panel, permanent audit trail) is implemented.
