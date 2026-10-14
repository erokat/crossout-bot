import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

SESSION_PATH = os.path.join(BASE_DIR, "session")
MEDIA_DIR = os.path.join(BASE_DIR, "media")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")
DB_PATH = os.path.join(BASE_DIR, "messages.db")
LOCK_PATH = os.path.join(BASE_DIR, "send.lock")
BOT_SENT_FILE = os.path.join(BASE_DIR, "bot_sent_ids.txt")

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)

def load_config():
    api_id = None
    api_hash = None
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
                api_id = c.get("api_id")
                api_hash = c.get("api_hash")
        except Exception:
            pass

    env_api_id = os.environ.get("TG_API_ID")
    if env_api_id:
        try:
            api_id = int(env_api_id)
        except ValueError:
            pass

    env_api_hash = os.environ.get("TG_API_HASH")
    if env_api_hash:
        api_hash = env_api_hash.strip()

    termux_config = os.path.expanduser("~/telegram_bridge/config.json")
    if (not api_id or not api_hash) and os.path.exists(termux_config):
        try:
            with open(termux_config, "r", encoding="utf-8") as f:
                c = json.load(f)
                if not api_id:
                    api_id = c.get("api_id")
                if not api_hash:
                    api_hash = c.get("api_hash")
        except Exception:
            pass

    bot_token = os.environ.get("CONTROL_BOT_TOKEN", "").strip()
    if not bot_token:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    bot_token = json.load(f).get("bot_token", "").strip()
            except Exception:
                pass
        if not bot_token and os.path.exists(termux_config):
            try:
                with open(termux_config, "r", encoding="utf-8") as f:
                    bot_token = json.load(f).get("bot_token", "").strip()
            except Exception:
                pass

    owner_id = int(os.environ.get("OWNER_ID", "5067025016"))

    yarik_chat_id = int(os.environ.get("YARIK_CHAT_ID", "6271387044"))
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

    return {
        "api_id": api_id,
        "api_hash": api_hash,
        "bot_token": bot_token,
        "owner_id": owner_id,
        "yarik_chat_id": yarik_chat_id,
        "render_url": render_url
    }
