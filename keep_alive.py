import os
import sys
import time
import json
import base64
import gzip
import shutil
import tarfile
import threading
import subprocess
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

from config import (
    BASE_DIR,
    SESSION_PATH,
    MEDIA_DIR,
    SAVED_MEMES_DIR,
    DB_PATH,
    BOT_SENT_FILE,
    load_config
)
from db import init_db, resolve_confirmation
from meme_generator import generate_crossout_meme
from gdrive import get_auth_url, exchange_code, upload_file_to_drive

def setup_environment():
    # 1. Decode SESSION_BASE64 if present
    sess_b64 = os.environ.get("SESSION_BASE64")
    if sess_b64:
        sess_file = SESSION_PATH if SESSION_PATH.endswith(".session") else f"{SESSION_PATH}.session"
        try:
            with open(sess_file, "wb") as f:
                f.write(base64.b64decode(sess_b64))
            os.chmod(sess_file, 0o600)
            print(f"[INIT] session.session decoded successfully to {sess_file}")
        except Exception as e:
            print(f"[INIT ERROR] Failed to decode SESSION_BASE64: {e}")

    # 2. Decode OAUTH_TOKEN_BASE64 if present
    oauth_b64 = os.environ.get("OAUTH_TOKEN_BASE64")
    if oauth_b64:
        oauth_dir = os.path.expanduser("~/.gemini/antigravity-cli")
        os.makedirs(oauth_dir, exist_ok=True)
        oauth_path = os.path.join(oauth_dir, "antigravity-oauth-token")
        try:
            with open(oauth_path, "wb") as f:
                f.write(base64.b64decode(oauth_b64))
            os.chmod(oauth_path, 0o600)
            print(f"[INIT] antigravity-oauth-token decoded successfully to {oauth_path}")
        except Exception as e:
            print(f"[INIT ERROR] Failed to decode OAUTH_TOKEN_BASE64: {e}")

    # 3. Create ~/.gemini/antigravity-cli/settings.json
    try:
        gemini_dir = os.path.expanduser("~/.gemini/antigravity-cli")
        os.makedirs(gemini_dir, exist_ok=True)
        settings_path = os.path.join(gemini_dir, "settings.json")
        settings_data = {
            "modelProvider": "gemini",
            "allowNonWorkspaceAccess": True,
            "toolPermission": "always-proceed",
            "artifactReviewPolicy": "always-proceed"
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=2)
        print(f"[INIT] settings.json configured at {settings_path}")
    except Exception as e:
        print(f"[INIT ERROR] Failed to write settings.json: {e}")

    # 4. Create config.json with TG API credentials
    try:
        cfg = load_config()
        cfg_path = os.path.join(BASE_DIR, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "api_id": cfg["api_id"],
                "api_hash": cfg["api_hash"]
            }, f, indent=2)
        print(f"[INIT] config.json configured at {cfg_path}")
    except Exception as e:
        print(f"[INIT ERROR] Failed to write config.json: {e}")

    # 5. Restore historical Antigravity session (de5ca636) and memory
    session_data_dir = os.path.join(BASE_DIR, "session_data")
    conv_gz = os.path.join(session_data_dir, "conversation.db.gz")
    conv_target_dir = os.path.expanduser("~/.gemini/antigravity-cli/conversations")
    conv_target = os.path.join(conv_target_dir, "de5ca636-4ede-4348-a756-2b4d4f01194a.db")
    if os.path.exists(conv_gz) and not os.path.exists(conv_target):
        try:
            os.makedirs(conv_target_dir, exist_ok=True)
            with gzip.open(conv_gz, "rb") as f_in, open(conv_target, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            print(f"[INIT] Historical conversation session restored to {conv_target}")
        except Exception as e:
            print(f"[INIT ERROR] Failed to restore conversation db: {e}")

    sum_src = os.path.join(session_data_dir, "conversation_summaries.db")
    sum_target = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
    if os.path.exists(sum_src) and not os.path.exists(sum_target):
        try:
            shutil.copy2(sum_src, sum_target)
            print(f"[INIT] conversation_summaries.db restored to {sum_target}")
        except Exception as e:
            print(f"[INIT ERROR] Failed to restore conversation_summaries: {e}")

    brain_tar = os.path.join(session_data_dir, "brain.tar.gz")
    brain_target_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain/de5ca636-4ede-4348-a756-2b4d4f01194a")
    if os.path.exists(brain_tar) and not os.path.exists(brain_target_dir):
        try:
            os.makedirs(brain_target_dir, exist_ok=True)
            with tarfile.open(brain_tar, "r:gz") as tar:
                tar.extractall(path=brain_target_dir)
            print(f"[INIT] Brain artifacts restored to {brain_target_dir}")
        except Exception as e:
            print(f"[INIT ERROR] Failed to restore brain artifacts: {e}")

    # Copy GEMINI.md to user global rules
    rule_src = os.path.join(BASE_DIR, "GEMINI.md")
    if os.path.exists(rule_src):
        for r_dest in [os.path.expanduser("~/.gemini/GEMINI.md"), os.path.expanduser("~/.gemini/config/GEMINI.md")]:
            try:
                os.makedirs(os.path.dirname(r_dest), exist_ok=True)
                shutil.copy2(rule_src, r_dest)
            except Exception:
                pass

    # 6. Initialize database
    init_db()

class WebServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress routine access logs to keep stdout clean
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ["/", "/health"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            resp = json.dumps({"status": "ok", "service": "yarik-crossout-userbot", "time": time.time()})
            self.wfile.write(resp.encode("utf-8"))
            return

        elif path == "/confirm":
            req_id = qs.get("id", [None])[0]
            action = qs.get("action", [None])[0]

            if req_id and action in ["approve", "reject"]:
                resolve_confirmation(req_id, action, comment="Web link click")
                status_text = "РАЗРЕШЕНО" if action == "approve" else "ОТКЛОНЕНО"
                badge_class = "badge-appr" if action == "approve" else "badge-rej"

                html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Решение принято</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f141c; color: #ffffff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .card {{ background: #1a2232; padding: 40px; border-radius: 16px; box-shadow: 0 8px 30px rgba(0,0,0,0.5); text-align: center; max-width: 450px; border: 1px solid #2a354b; }}
        h1 {{ margin-bottom: 12px; font-size: 26px; }}
        p {{ color: #9aa5b8; font-size: 16px; margin: 8px 0; }}
        .badge {{ display: inline-block; padding: 10px 24px; border-radius: 30px; font-weight: bold; margin-top: 20px; font-size: 18px; letter-spacing: 1px; }}
        .badge-appr {{ background: #10b981; color: #fff; }}
        .badge-rej {{ background: #ef4444; color: #fff; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>✅ Решение принято!</h1>
        <p>Запрос <code>{req_id}</code> успешно обработан.</p>
        <div class="badge {badge_class}">{status_text}</div>
    </div>
</body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
                return
            else:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Bad Request: Missing or invalid id/action parameters.")
                return

        elif path == "/gdrive/connect":
            auth_url = get_auth_url()
            if auth_url:
                self.send_response(302)
                self.send_header("Location", auth_url)
                self.end_headers()
                return
            else:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"GDRIVE_CLIENT_ID not configured.")
                return

        elif path == "/oauth/google/callback":
            code = qs.get("code", [None])[0]
            error = qs.get("error", [None])[0]

            if error:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>Ошибка авторизации Google: {error}</h1>".encode("utf-8"))
                return

            if code:
                success, msg = exchange_code(code)
                if success:
                    def sync_all():
                        if os.path.exists(SAVED_MEMES_DIR):
                            for f in os.listdir(SAVED_MEMES_DIR):
                                if f.endswith((".png", ".jpg", ".gif")):
                                    upload_file_to_drive(os.path.join(SAVED_MEMES_DIR, f))
                    threading.Thread(target=sync_all, daemon=True).start()

                    cfg = load_config()
                    if cfg.get("bot_token") and cfg.get("owner_id"):
                        cmd = [
                            sys.executable,
                            os.path.join(BASE_DIR, "send.py"),
                            "--to", "owner",
                            "--text", "🎉 <b>Google Диск успешно подключен!</b>\nПапка <code>memes</code> создана. Все сохраненные и новые мемы теперь автоматически синхронизируются с твоим личным Google Диском! 📁☁️"
                        ]
                        subprocess.run(cmd)

                    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Google Диск подключен</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
        .card { background: #1e293b; border-radius: 16px; padding: 32px; max-width: 440px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; }
        h1 { margin-top: 0; font-size: 24px; color: #38bdf8; }
        p { color: #94a3b8; font-size: 15px; line-height: 1.5; }
        .badge { display: inline-block; padding: 6px 14px; border-radius: 9999px; font-weight: bold; font-size: 14px; margin-bottom: 16px; background: #166534; color: #4ade80; }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">СИНХРОНИЗАЦИЯ АКТИВНА</div>
        <h1>✅ Google Диск подключен!</h1>
        <p>Папка <b>memes</b> успешно создана в твоем Google Диске. Все создаваемые мемы бота будут автоматически загружаться туда в фоне.</p>
        <p>Можешь закрыть эту вкладку и вернуться в Telegram.</p>
    </div>
</body>
</html>"""
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                    return
                else:
                    self.send_response(500)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(f"<h1>Ошибка обмена токена:</h1><p>{msg}</p>".encode("utf-8"))
                    return

        self.send_response(404)
        self.end_headers()

def run_http_server(port):
    server = HTTPServer(("0.0.0.0", port), WebServerHandler)
    print(f"[HTTP] Server listening on 0.0.0.0:{port}")
    server.serve_forever()

def run_self_pinger(render_url):
    if not render_url:
        return
    print(f"[PINGER] Background self-pinger active for: {render_url}")
    while True:
        time.sleep(300) # 5 minutes
        try:
            url = f"{render_url}/health"
            req = urllib.request.Request(url, headers={"User-Agent": "CrossoutBot-Pinger/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                pass
            print(f"[PINGER] Keep-alive ping sent to {url}")
        except Exception as e:
            print(f"[PINGER WARNING] Ping failed: {e}")

def cleanup_video_file(file_path):
    """Deletes downloaded video/TikTok from disk after viewing/processing to save memory."""
    if not file_path:
        return
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".ts"]:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[CLEANUP] Deleted processed video to free memory: {file_path}")
    except Exception as e:
        print(f"[CLEANUP WARNING] Failed to delete video {file_path}: {e}")

def run_periodic_media_cleaner():
    """Background daemon that sweeps media folder every 5 minutes and purges leftover videos."""
    while True:
        time.sleep(300)
        try:
            now = time.time()
            if os.path.exists(MEDIA_DIR):
                for f in os.listdir(MEDIA_DIR):
                    fpath = os.path.join(MEDIA_DIR, f)
                    if not os.path.isfile(fpath):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    if (ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".ts"] or f.startswith("tmp_")) and (now - os.path.getmtime(fpath) > 120):
                        try:
                            os.remove(fpath)
                            print(f"[AUTO-CLEANUP] Purged cached file: {f}")
                        except Exception:
                            pass
        except Exception as e:
            print(f"[CLEANUP EXCEPTION] Error in periodic cleaner: {e}")

def run_antigravity_cli(prompt):
    conv_id = "de5ca636-4ede-4348-a756-2b4d4f01194a"
    conv_db = os.path.expanduser(f"~/.gemini/antigravity-cli/conversations/{conv_id}.db")

    # If historical conversation session is loaded, continue it!
    if os.path.exists(conv_db):
        cmd = ["agy", "--dangerously-skip-permissions", f"--conversation={conv_id}", "-p", prompt]
    else:
        cmd = ["agy", "--dangerously-skip-permissions", "-p", prompt]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        if res.returncode == 0:
            return res.stdout.strip()
        else:
            print(f"[AGY WARNING] Error running agy: {res.stderr}")
            if f"--conversation={conv_id}" in cmd:
                fb_cmd = ["agy", "--dangerously-skip-permissions", "-p", prompt]
                fb_res = subprocess.run(fb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                if fb_res.returncode == 0:
                    return fb_res.stdout.strip()
            return None
    except Exception as e:
        print(f"[AGY EXCEPTION] Failed to execute agy: {e}")
        return None

def get_last_bot_sent_id():
    if not os.path.exists(BOT_SENT_FILE):
        return None
    try:
        with open(BOT_SENT_FILE, "r") as f:
            ids = [int(line.strip()) for line in f if line.strip().isdigit()]
            return ids[-1] if ids else None
    except Exception:
        return None

def handle_owner_message(msg_data):
    text = msg_data.get("text", "").strip()
    photo = msg_data.get("photo")
    t_lower = text.lower()
    print(f"[ORCHESTRATOR] Handling OWNER task: {text!r} (photo={photo})")

    # If owner asks for a meme
    if any(w in t_lower for w in ["мем", "пикч", "картинк", "гиф"]):
        meme_path = generate_crossout_meme(theme=text)
        cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "owner",
            "--photo", meme_path,
            "--text", "Ваш мем готов, командир! 🚜💥"
        ]
        subprocess.run(cmd)
        return

    # 1. Запрос ссылки на стикерпак от владельца
    is_owner_stk_req = any(w in t_lower for w in ["стикерпак", "стикеры", "стикер"]) or "пак" in t_lower
    is_owner_stk_send = any(w in t_lower for w in ["скинь", "дай", "где", "ссылк", "линк", "покажи", "кинь", "сбрось", "отправь", "поделись"])
    is_owner_stk_add = any(w in t_lower for w in ["добавь", "закинь", "запили", "в пак", "в стикерпак"])

    if is_owner_stk_req and not is_owner_stk_add and (is_owner_stk_send or "стикерпак" in t_lower or "стикеры" in t_lower):
        prompt_stk = (
            "Владелец бота попросил скинуть ссылку на наш стикерпак Crossout: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
            "Ответь живо, дружелюбно, по-товарищески (1-2 коротких предложения), мол держи коллекцию, шеф. "
            "Обязательно включи ссылку: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat"
        )
        reply = run_antigravity_cli(prompt_stk)
        if not reply or "https://t.me/addstickers/crossout_memes_arhfb8_by_erokat" not in reply:
            reply = "Держи наш стикерпак, шеф! Раздавай стиль в чатах: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat 🔥🚜"
        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # 2. Добавление мема в стикерпак по просьбе владельца
    if is_owner_stk_req and is_owner_stk_add:
        recent_memes = sorted([
            os.path.join(SAVED_MEMES_DIR, f) for f in os.listdir(SAVED_MEMES_DIR)
            if f.endswith((".png", ".jpg"))
        ], key=os.path.getmtime, reverse=True) if os.path.exists(SAVED_MEMES_DIR) else []
        if recent_memes:
            sticker_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "add_to_sticker_pack.py"),
                "--image", recent_memes[0]
            ]
            subprocess.run(sticker_cmd)
            reply = "Добавил последний мем в стикерпак! 🔥"
        else:
            reply = "В папке saved_memes пока нет мемов для добавления в стикерпак."
        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # If owner asks for status or health
    if any(w in t_lower for w in ["статус", "status", "пинг", "ping", "инфо"]):
        reply = "🟢 Сервер Render активен 24/7! Все службы юзербота, Bot API и Telethon на дежурстве."
        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # If owner asks for Google Drive connection
    if any(w in t_lower for w in ["диск", "drive", "gdrive"]):
        connect_url = "https://yarik-crossout-userbot.onrender.com/gdrive/connect"
        reply = (
            "📁 <b>Подключение Google Диска:</b>\n\n"
            f"Перейди по ссылке для разовой авторизации:\n"
            f"👉 <a href='{connect_url}'>Нажми сюда, чтобы войти через Google</a>\n\n"
            "После подтверждения бот автоматически создаст папку <code>memes</code> на твоем Диске и загрузит туда все созданные мемы!"
        )
        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # Run Antigravity CLI or smart helper
    response = None
    if text:
        prompt = f"Ты умный и преданный помощник владельца (erokat). Владелец написал тебе в личку: «{text}». Ответь четко, по делу, дружелюбно и живо, без шаблонных канцеляризмов."
        response = run_antigravity_cli(prompt)

    if not response:
        response = f"Принял, шеф! Задача по «{text}» в работе. Все службы на связи 🫡"

    # Reply to owner
    cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", response]
    subprocess.run(cmd)

def handle_yarik_message(msg_data, chat_title="Ярик"):
    msg_id = msg_data.get("id")
    text = msg_data.get("text", "").strip()
    t_lower = text.lower()
    print(f"[ORCHESTRATOR] Handling YARIK summon: {text!r} (msg_id={msg_id})")

    # 1. Запрос на удаление
    if "удали" in t_lower:
        target_id = msg_data.get("reply_to_msg_id") or get_last_bot_sent_id()
        ask_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "ask_owner.py"),
            f"Ярик просит удалить сообщение{' #' + str(target_id) if target_id else ''} в чате: «{text}»"
        ]
        res = subprocess.run(ask_cmd, stdout=subprocess.PIPE, text=True)
        approved = False
        owner_comment = ""
        try:
            parsed_verdict = json.loads(res.stdout.strip())
            approved = (parsed_verdict.get("verdict") == "APPROVED")
            owner_comment = parsed_verdict.get("comment", "")
        except Exception:
            approved = ("APPROVED" in res.stdout)

        if approved:
            if target_id:
                del_cmd = [
                    sys.executable,
                    os.path.join(BASE_DIR, "send.py"),
                    "--to", "yarik",
                    "--delete", str(target_id)
                ]
                subprocess.run(del_cmd)
            
            prompt_appr = (
                f"Ярик попросил в чате удалить сообщение ('{text}'). Владелец разрешил, и ты только что снес его к чертям из чата у всех (у обоих). "
                "Напиши живой, угарный, саркастичный ответ Ярику в чат в стиле опытного игрока Crossout (без официоза, без щитов '🛡️', по-пацански, "
                "про детонацию, зачистку ангара или замятый позор, мол никто ничего не видел). 1-2 сочных предложения. Выдай ТОЛЬКО сам текст реплики."
            )
            reply = run_antigravity_cli(prompt_appr)
            if not reply:
                reply = "Стер этот позор к чертям у всех, будто Газген сдетонировал в упор 💥 Ярик, спи спокойно, свидетелей нет."
        else:
            reason_str = f", сказав: '{owner_comment}'" if (owner_comment and owner_comment not in ["Inline button", "Web link click"] and not owner_comment.startswith("Timeout")) else ""
            prompt_rej = (
                f"Ярик просил удалить сообщение ('{text}'), но владелец отказал{reason_str}. "
                "Напиши живой, саркастичный и смешной ответ Ярику в чат (без официоза '⚠️ Владелец отклонил', по-дружески подколи его, мол, этот шедевр останется для истории Пустошей). "
                "1-2 предложения. Выдай ТОЛЬКО сам текст реплики."
            )
            reply = run_antigravity_cli(prompt_rej)
            if not reply:
                if reason_str:
                    reply = f"Не-а, шеф наложил вето: «{owner_comment}» 😂 Так что любуйся своим шедевром."
                else:
                    reply = "Шеф сказал оставить для потомков 😂 Этот легендарный высер останется в истории Пустошей!"

        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--text", reply,
            "--reply-to", str(msg_id)
        ]
        subprocess.run(send_cmd)
        return

    # 2. Запрос на мем / картинку
    if any(w in t_lower for w in ["мем", "пикч", "картинк", "гиф", "сделай"]):
        meme_path = generate_crossout_meme(theme=text)
        prompt_cap = (
            f"Ты генератор мемов по игре Crossout. Придумай одну смешную, угарную, жизненную подпись к мему по теме: «{text}». "
            "В стиле игроков Crossout (с сарказмом про рандом, взрывы, автосборку, детонацию крафтов). Без кавычек, 1 короткое сочное предложение с эмодзи."
        )
        caption = run_antigravity_cli(prompt_cap)
        if not caption:
            caption = "Когда собрал крафт из говна и палок и поехал тащить рандом 🚜💀"

        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--photo", meme_path,
            "--text", caption,
            "--reply-to", str(msg_id)
        ]
        subprocess.run(send_cmd)

        # Если просили добавить в стикерпак
        if any(w in t_lower for w in ["стикер", "пак"]) and any(w in t_lower for w in ["добавь", "закинь", "в стикерпак", "в пак"]):
            sticker_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "add_to_sticker_pack.py"),
                "--image", meme_path
            ]
            subprocess.run(sticker_cmd)
            prompt_stk = "Ярик попросил добавить созданный мем в стикерпак Crossout. Ты только что закинул его в пак. Напиши короткую живую фразу в чат (1 предложение), что мем добавлен в стикерпак и готов к спаму."
            stk_reply = run_antigravity_cli(prompt_stk) or "Закинул этот угар в стикерпак! Теперь можно спамить в чатах 🔥💀"
            confirm_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "yarik",
                "--text", stk_reply,
                "--reply-to", str(msg_id)
            ]
            subprocess.run(confirm_cmd)
        return

    # 3. Запрос на отправку ссылки на стикерпак (живой разговорный ответ)
    is_stk_req = any(w in t_lower for w in ["стикерпак", "стикеры", "стикер"]) or ("пак" in t_lower and any(w in t_lower for w in ["скинь", "дай", "где", "ссылк", "линк", "кинь"]))
    is_stk_send = any(w in t_lower for w in ["скинь", "дай", "где", "ссылк", "линк", "покажи", "кинь", "сбрось", "отправь", "поделись", "кидай", "скидывай"])
    is_stk_add = any(w in t_lower for w in ["добавь", "закинь", "запили", "засунь", "в пак", "в стикерпак"])

    if is_stk_req and not is_stk_add and (is_stk_send or "стикерпак" in t_lower or "стикеры" in t_lower):
        prompt_stk_share = (
            "Ярик в чате попросил скинуть ссылку на наш стикерпак по игре Crossout: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
            f"Его сообщение: «{text}»\n"
            "Напиши угарный, живой, пацанский ответ корешу в чат (1-2 предложения), как реальный заядлый игрок в Crossout "
            "(с юмором, сарказмом и иронией про взрывы Газгенов, рандомных раков, позор Пустошей, мол держи святой артефакт и спамь на здоровье). "
            "Категорически без официоза, без шаблонных фраз роботов (типа 'Вот ваша ссылка' или 'Вот ссылка на стикерпак'). "
            "ОБЯЗАТЕЛЬНО включи саму ссылку: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
            "Выдай ТОЛЬКО чистый текст реплики в чат."
        )
        reply = run_antigravity_cli(prompt_stk_share)
        if not reply or "https://t.me/addstickers/crossout_memes_arhfb8_by_erokat" not in reply:
            reply = "Держи наш склад отборного позора и детонаций, спамь пока раму не оторвало: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat 🔥🚜"

        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--text", reply,
            "--reply-to", str(msg_id)
        ]
        subprocess.run(send_cmd)
        return

    # 4. Добавление в стикерпак отдельной командой (добавь в стикерпак)
    if is_stk_req and is_stk_add:
        recent_memes = sorted([
            os.path.join(SAVED_MEMES_DIR, f) for f in os.listdir(SAVED_MEMES_DIR)
            if f.endswith((".png", ".jpg"))
        ], key=os.path.getmtime, reverse=True) if os.path.exists(SAVED_MEMES_DIR) else []

        if recent_memes:
            sticker_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "add_to_sticker_pack.py"),
                "--image", recent_memes[0]
            ]
            subprocess.run(sticker_cmd)
            prompt_stk = "Ты только что добавил последний мем в стикерпак по просьбе Ярика. Напиши живую, короткую фразу (1 предложение) в стиле Crossout про добавление в стикерпак."
            stk_reply = run_antigravity_cli(prompt_stk) or "Закинул этот угар в стикерпак, шедевр зафиксирован в ангаре! 🔥"
            confirm_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "yarik",
                "--text", stk_reply,
                "--reply-to", str(msg_id)
            ]
            subprocess.run(confirm_cmd)
        else:
            send_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "yarik",
                "--text", "Так у нас в ангаре пусто, Ярик! Сначала сделай мем, а потом уже в стикерпак пихать будем 🚜",
                "--reply-to", str(msg_id)
            ]
            subprocess.run(send_cmd)
        return

    # 5. Общий живой разговорный ответ по Crossout
    prompt = (
        f"Ты — юзербот и кореш Ярика в чате (играете вместе в Crossout). Ярик написал тебе: «{text}». "
        "Ответь ему как живой пацан-геймер, с юмором, сарказмом и сленгом Crossout (газгены, ховеры, утюги, рандом, крафты), а не как робот-помощник! "
        "Коротко, на «ты», без душности, без фраз 'Я бот, чем помочь' и без официоза. Только сам текст живой реплики в чат."
    )
    answer = run_antigravity_cli(prompt)
    if not answer:
        answer = "Че кого, Ярик? 🚜 Пока ты в гараже крафт пересобираешь, твой Газген уже на грани детонации. Гоняй в бой или кидай тему для мема!"

    send_cmd = [
        sys.executable,
        os.path.join(BASE_DIR, "send.py"),
        "--to", "yarik",
        "--text", answer,
        "--reply-to", str(msg_id)
    ]
    subprocess.run(send_cmd)

def main():
    print("=" * 60)
    print("🚀 Starting Crossout Userbot Orchestrator 24/7 (Render Edition)")
    print("=" * 60)

    setup_environment()
    cfg = load_config()

    port = int(os.environ.get("PORT", 10000))
    http_thread = threading.Thread(target=run_http_server, args=(port,), daemon=True)
    http_thread.start()

    render_url = cfg.get("render_url")
    if render_url:
        pinger_thread = threading.Thread(target=run_self_pinger, args=(render_url,), daemon=True)
        pinger_thread.start()

    cleaner_thread = threading.Thread(target=run_periodic_media_cleaner, daemon=True)
    cleaner_thread.start()

    print("[ORCHESTRATOR] Main duty loop started...")

    while True:
        try:
            cmd = [sys.executable, os.path.join(BASE_DIR, "wait_for_yarik.py"), "--timeout", "900"]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            stdout = proc.stdout.strip()
            if not stdout:
                time.sleep(1)
                continue

            try:
                data = json.loads(stdout)
            except Exception:
                # In case extra lines were printed, find the JSON line
                data = None
                for line in stdout.splitlines():
                    try:
                        data = json.loads(line.strip())
                        break
                    except Exception:
                        continue

            if not data or data.get("status") != "new_messages":
                time.sleep(1)
                continue

            source = data.get("source")
            messages = data.get("messages", [])

            for m in messages:
                try:
                    if source == "owner":
                        handle_owner_message(m)
                    elif source == "yarik":
                        handle_yarik_message(m, chat_title=data.get("chat_title", "Ярик"))
                finally:
                    # After viewing/processing TikTok or any video, immediately delete to save disk/memory
                    vid_candidate = m.get("video") or (m.get("photo") if (m.get("photo") and m.get("photo").lower().endswith((".mp4", ".mov", ".avi", ".webm", ".mkv", ".ts"))) else None)
                    if vid_candidate:
                        cleanup_video_file(vid_candidate)

        except Exception as e:
            print(f"[ORCHESTRATOR EXCEPTION] Unexpected error in duty loop: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
