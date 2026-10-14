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
import re
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
from db import init_db, resolve_confirmation, get_confirmation
from meme_generator import generate_crossout_meme
from gdrive import get_auth_url, exchange_code, upload_file_to_drive
from dynamic_agent import is_autonomous_task, execute_autonomous_task

def delete_bot_message(bot_token, chat_id, message_id):
    if not bot_token or not chat_id or not message_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
    payload = {"chat_id": chat_id, "message_id": int(message_id)}
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        sys.stderr.write(f"Failed to delete bot message {message_id}: {e}\n")
        return False

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
                conf = get_confirmation(req_id)
                cfg = load_config()
                bot_token = cfg.get("bot_token")
                owner_id = cfg.get("owner_id")
                if conf and conf.get("message_id") and bot_token and owner_id:
                    delete_bot_message(bot_token, owner_id, conf["message_id"])
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

def ask_gemini_api(prompt, photo_path=None, system_instruction=None):
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        parts = []
        if photo_path and os.path.exists(photo_path):
            mime = "image/jpeg" if photo_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
            with open(photo_path, "rb") as f:
                b64_img = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"inlineData": {"mimeType": mime, "data": b64_img}})
        parts.append({"text": prompt})
        body = {"contents": [{"parts": parts}]}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            candidates = res_data.get("candidates", [])
            if candidates:
                parts_out = candidates[0].get("content", {}).get("parts", [])
                out_texts = [p.get("text", "") for p in parts_out if "text" in p]
                if out_texts:
                    return "".join(out_texts).strip()
    except Exception as e:
        print(f"[GEMINI API EXCEPTION] {e}")
    return None

def ocr_image_file(photo_path):
    if not photo_path or not os.path.exists(photo_path):
        return ""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(photo_path)
        try:
            txt = pytesseract.image_to_string(img, lang="ron+rus+eng").strip()
        except Exception:
            txt = pytesseract.image_to_string(img).strip()
        return txt
    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return ""

def run_antigravity_cli(prompt):
    agy_bin = shutil.which("agy") or shutil.which("antigravity")
    if not agy_bin:
        for candidate in ["/usr/local/bin/agy", "/root/.local/bin/agy", "/data/data/com.termux/files/usr/bin/agy"]:
            if os.path.exists(candidate):
                agy_bin = candidate
                break
    if not agy_bin:
        agy_bin = "agy"

    cmd = [agy_bin, "--dangerously-skip-permissions", "-p", prompt]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        else:
            if res.stderr:
                print(f"[AGY WARNING] Error running {agy_bin}: {res.stderr[:200]}")
            return None
    except Exception as e:
        print(f"[AGY EXCEPTION] Failed to execute {agy_bin}: {e}")
        return None

def ask_ai(prompt, photo_path=None, system_instruction=None):
    # 1. Try Gemini API directly if configured
    gemini_res = ask_gemini_api(prompt, photo_path=photo_path, system_instruction=system_instruction)
    if gemini_res:
        return gemini_res

    # 2. If photo is present and no Gemini API, extract text via OCR
    ocr_text = ""
    if photo_path and os.path.exists(photo_path):
        ocr_text = ocr_image_file(photo_path)

    combined_prompt = prompt
    if ocr_text:
        combined_prompt = f"Текст с прикрепленной фотографии задания/учебника:\n«««\n{ocr_text}\n»»»\n\nЗапрос пользователя: {prompt}"
    if system_instruction:
        combined_prompt = f"{system_instruction}\n\n{combined_prompt}"

    # 3. Call Antigravity CLI
    return run_antigravity_cli(combined_prompt)

def is_homework_or_study(text, has_photo=False):
    if not text and not has_photo:
        return False
    t = text.lower().strip()
    hw_words = [
        "дз", "домашк", "домашка", "домашнее", "переведи", "перевод", "реши",
        "помоги с", "задач", "номер", "упражнен", "сочинен", "эссе", "изложен",
        "молдавск", "румынск", "английск", "немецк", "французск", "математ",
        "алгебр", "геометр", "физик", "хими", "биолог", "истори", "географ",
        "литератур", "правил", "как переводится", "что значит", "разбери слово",
        "морфологическ", "синтаксическ", "падеж", "спряжен", "уравнен", "теорем",
        "интеграл", "производн", "корень", "дробь", "диктант", "урок", "реферат",
        "ответь на вопрос", "параграф"
    ]
    if any(w in t for w in hw_words):
        return True
    if has_photo and any(w in t for w in ["что тут", "что это", "помоги", "напиши", "сделай", "разбери", "текст", "перевод", "реши", "прочитай"]):
        return True
    return False

def solve_school_task(text, photo_path=None, is_owner=False, sender_name="Ярик"):
    t_lower = text.lower()
    is_essay = any(w in t_lower for w in ["сочинен", "эссе", "изложен"])
    is_trans = any(w in t_lower for w in ["переведи", "перевод", "молдавск", "румынск", "английск", "немецк", "французск", "как переводится"])

    target_name = "Миша" if is_owner else "Ярик"

    if is_essay:
        system_instruction = (
            "Ты — опытный репетитор по русскому языку и литературе. Напиши образцовое школьное сочинение, строго соблюдая структуру:\n"
            "1. Вступление (тезис, 3-5 предложений): определение ключевого понятия своими словами, постановка проблемы и четкий тезис.\n"
            "2. Основная часть (литературный аргумент, 8-14 предложений): глубокий анализ ОДНОГО конкретного героя и ОДНОГО произведения, указать ФИО автора, название, жанр, мотивы героя, ключевой конфликт и финал.\n"
            "3. Заключение (3-5 предложений): актуальность проблемы для современного человека и обобщающий вывод.\n"
            "Стиль: живой, грамотный язык реального ученика-старшеклассника, без канцеляризмов и штампов. Без выдуманных фактов."
        )
        prompt = f"Напиши школьное сочинение на тему: «{text}»."
    elif is_trans:
        system_instruction = (
            "Ты — профессиональный переводчик и преподаватель языков. Твоя задача — максимально точно, грамотно и качественно перевести текст для школьника. "
            "Если текст на молдавском / румынском языке, переведи его на чистый литературный русский язык. "
            "Структура ответа:\n"
            "1. Перевод на русский язык (четкий, связный, грамотный).\n"
            "2. Если переводишь с фото — приведи оригинальный текст и перевод каждого абзаца/предложения.\n"
            "3. Если есть сложные или интересные слова/грамматика — кратко поясни их значение."
        )
        prompt = f"Переведи задание/текст: «{text}»."
    else:
        system_instruction = (
            "Ты — умный и доброжелательный школьный репетитор по всем предметам (математика, физика, химия, русский язык, биология, история). "
            "Твоя задача — помочь ученику разобраться с домашним заданием. "
            "Объясняй понятно, по шагам, с формулами и пояснениями. В конце обязательно выдели четкий ОТВЕТ. "
            "Будь вежливым, поддерживающим и конструктивным. Никакого геймерского сленга и дурацких шуток."
        )
        prompt = f"Помоги решить школьное задание / домашку: «{text}»."

    solution = ask_ai(prompt, photo_path=photo_path, system_instruction=system_instruction)

    if not solution:
        if photo_path:
            return (
                f"{target_name}, я попытался разобрать фото с заданием, но не смог четко распознать текст. "
                "Пожалуйста, сфотографируй страницу ближе и четче (при хорошем освещении) или напиши само задание текстом — я сразу всё решу!"
            )
        else:
            return f"{target_name}, напиши чуть подробнее условие задания или номер упражнения — я помогу решить и всё объясню по полочкам!"

    prefix = f"📚 **Домашка для {target_name}:**\n\n"
    if is_trans:
        prefix = f"🌐 **Перевод для {target_name}:**\n\n"
    elif is_essay:
        prefix = f"📝 **Сочинение для {target_name}:**\n\n"

    solution = re.sub(r"\bшеф[а-я]*\b", "Миша", solution, flags=re.I)
    solution = re.sub(r"\bбосс[а-я]*\b", "Миша", solution, flags=re.I)

    return prefix + solution

def search_youtube_video(query):
    try:
        clean_q = re.sub(r"(?:найди|поищи|скинь|в|на|ютубе|ютуб|youtube|ссылку|этот|момент|бот|ботик)\s*", " ", query, flags=re.I).strip()
        if not clean_q:
            clean_q = query
        encoded = urllib.parse.quote(clean_q)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
        matches = re.findall(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\".*?\"title\":\{\"runs\":\[\{\"text\":\"([^\"]+)\"\}\]", html)
        if matches:
            vid, title = matches[0]
            return f"https://www.youtube.com/watch?v={vid}", title
    except Exception as e:
        print(f"[YOUTUBE SEARCH ERROR] {e}")
    return None, None

def get_last_bot_sent_id():
    if not os.path.exists(BOT_SENT_FILE):
        return None
    try:
        with open(BOT_SENT_FILE, "r") as f:
            ids = [int(line.strip()) for line in f if line.strip().isdigit()]
            return ids[-1] if ids else None
    except Exception:
        return None

def extract_meme_count(text):
    if not text:
        return 1
    t = text.lower()
    # 1. Number before meme word: "3 мема", "3 мэмасика", "5 картинок"
    m = re.search(r"(\d+)\s*(?:мем|мэм|пикч|картинк|штук)", t)
    if m:
        return max(1, min(int(m.group(1)), 10))
    # 2. Number after meme word (e.g. "мемов по кросауту 3", "мэмасиков 3", "пикчи 2")
    m = re.search(r"(?:мем[а-я]*|мэм[а-я]*|пикч[а-я]*|картинк[а-я]*|штук[а-я]*)\D*?(\d+)", t)
    if m:
        return max(1, min(int(m.group(1)), 10))
    # 3. Any standalone number in text if meme keyword is present
    if any(w in t for w in ["мем", "мэм", "пикч", "картинк", "гиф"]):
        m = re.search(r"\b(\d+)\b", t)
        if m:
            return max(1, min(int(m.group(1)), 10))
    # 4. Words for numbers
    num_words = {
        "два": 2, "две": 2, "пару": 2, "три": 3, "четыре": 4, "пять": 5,
        "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10
    }
    for word, val in num_words.items():
        if re.search(rf"\b{word}\b", t):
            return val
    return 1

def handle_owner_message(msg_data):
    text = msg_data.get("text", "").strip()
    photo = msg_data.get("photo")
    t_lower = text.lower()
    print(f"[ORCHESTRATOR] Handling OWNER task: {text!r} (photo={photo})")

    meme_words = ["мем", "мэм", "пикч", "картинк", "гиф"]
    is_meme_theme_req = any(w in t_lower for w in ["выбирай сам", "сам придумай", "на твой вкус", "на свой вкус", "на свой выбор", "на твое усмотрение"])
    has_meme_mention = any(w in t_lower for w in meme_words) or is_meme_theme_req

    # 0. Команда отправить текущий / последний созданный мем Ярику
    # Срабатывает ТОЛЬКО если это явная команда отправить УЖЕ показанный мем (например, "отправляй ему", "кидай ему", или реплай "отправляй", "скинь")
    # И НЕ содержит запрос на создание новых мемов ("отправь ярику 3 мема" — это создание!)
    is_reply_forward = bool(msg_data.get("reply_to_msg_id")) and any(w in t_lower for w in ["отправляй", "отпраляй", "отправь", "скинь", "кинь", "шли", "давай", "норм", "пойдет", "годится"])
    is_explicit_forward = any(w in t_lower for w in [
        "отправляй ему", "отпраляй ему", "отправь ему", "скинь ему", "кидай ему", "кинь ему",
        "перешли ему", "закинь ему", "шли ему", "запули ему", "давай ему", "отправляй это ярику",
        "скинь это ярику", "кидай это ярику"
    ])
    is_forward_to_yarik = (is_reply_forward or is_explicit_forward) and not any(w in t_lower for w in ["новый", "новых", "свеж", "3", "2", "4", "5", "три", "два", "пять"])

    if is_forward_to_yarik:
        recent_memes = sorted([
            os.path.join(SAVED_MEMES_DIR, f) for f in os.listdir(SAVED_MEMES_DIR)
            if f.endswith((".png", ".jpg"))
        ], key=os.path.getmtime, reverse=True) if os.path.exists(SAVED_MEMES_DIR) else []

        if recent_memes:
            meme_path = recent_memes[0]
        else:
            # Если мемов в памяти нет — автоматически генерируем новый и не отказываем!
            meme_path = generate_crossout_meme(theme="Crossout random madness", allow_repeat=False, recipient="yarik")

        prompt_cap = "Ты отправляешь свежий мем Ярику в чат по поручению своего друга (создателя). Напиши короткую живую пацанскую реплику Ярику (1 предложение) в стиле игроков Crossout про рандом и крафты. Выдай ТОЛЬКО текст."
        caption = ask_ai(prompt_cap) or "Ярик, зацени этот шедевр! Требуется твоя строгая экспертная оценка от 1 до 10 💥🚜"

        cmd_yarik = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "yarik", "--photo", meme_path, "--text", caption]
        subprocess.run(cmd_yarik)

        cmd_owner = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "owner",
            "--text", "Всё, запулил этот мем Ярику в чат! Ждем реакцию 🔥🚜"
        ]
        subprocess.run(cmd_owner)
    # 0.5. Поиск видео / момента / клипа на YouTube для владельца
    is_search_video = any(w in t_lower for w in ["найди", "поищи", "ютуб", "youtube", "откуда", "что за видео", "что за момент", "оригинал"]) and any(w in t_lower for w in ["момент", "видео", "клип", "ютуб", "youtube", "сери", "серия", "фильм", "мульт", "скинь", "ссылк", "линк"])
    if is_search_video:
        prompt_q = f"Пользователь просит найти видео/момент: «{text}». Какое название видео/мультфильма/момента нужно ввести в YouTube для поиска? Выдай ТОЛЬКО 2-4 ключевых слова для поиска на YouTube без кавычек."
        search_kw = ask_ai(prompt_q) or text
        vid_url, vid_title = search_youtube_video(search_kw)
        if not vid_url:
            vid_url, vid_title = search_youtube_video(text)

        if vid_url:
            reply_search = f"Держи этот момент на YouTube, Миша:\n🎬 {vid_title}\n👉 {vid_url}"
        else:
            reply_search = f"Попробовал поискать на YouTube, Миша, но точный ролик не нашелся. Попробуй уточнить название или персонажа!"

        cmd_owner = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "owner",
            "--text", reply_search
        ]
        subprocess.run(cmd_owner)
        return

    # 0.6. Домашнее задание / решение задач / перевод текста / учеба
    if is_homework_or_study(text, has_photo=bool(photo)):
        answer = solve_school_task(text, photo_path=photo, is_owner=True, sender_name="Миша")
        cmd_owner = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "owner",
            "--text", answer
        ]
        subprocess.run(cmd_owner)
        return

    # 0.7. Автономная генерация кода / создание новых функций / выполнение задач (Antigravity Agent)
    if is_autonomous_task(text):
        res_text, res_media = execute_autonomous_task(text, sender_name="Миша", photo_path=photo, ask_ai_fn=ask_ai)
        cmd_owner = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner"]
        if res_media and os.path.exists(res_media):
            cmd_owner.extend(["--photo", res_media, "--text", res_text])
        else:
            cmd_owner.extend(["--text", res_text])
        subprocess.run(cmd_owner)
        return

    # 1. Поручение отправить что-то Ярику (мем или сообщение)
    is_yarik_dest = any(w in t_lower for w in ["ярик", "ярику", "кореш"]) or is_meme_theme_req
    if is_yarik_dest:
        if has_meme_mention:
            is_repeat = any(w in t_lower for w in ["заново", "снова", "повтори", "тот же", "тот самый", "продублируй", "еще раз", "ещё раз", "тоже самое"])
            count = extract_meme_count(text)
            last_meme = None
            for idx in range(count):
                meme_path = generate_crossout_meme(theme=text, allow_repeat=is_repeat, recipient="yarik")
                last_meme = meme_path
                num_suffix = f" (#{idx + 1})" if count > 1 else ""
                prompt_cap = (
                    f"Владелец бота поручил отправить Ярику мем{num_suffix} по теме: «{text}». "
                    "Напиши короткую, живую, угарную подпись корешу в чат (1-2 предложения), как реальный заядлый геймер в тему этого мема, "
                    "и попроси его дать строгую экспертную оценку этому шедевру. Выдай ТОЛЬКО текст реплики."
                )
                if any(w in t_lower for w in ["рэин", "рейн", "rain", "слизн", "скэв"]):
                    fb_cap = f"Ярик, зацени этот шедевр по Rain World{num_suffix}! Требуется твоя строгая экспертная оценка от 1 до 10 🌧️🐱"
                else:
                    fb_cap = f"Ярик, зацени этот шедевр{num_suffix}! Требуется твоя строгая экспертная оценка от 1 до 10 🔥🚜"
                caption = ask_ai(prompt_cap) or fb_cap

                # Отправка Ярику через Telethon
                cmd_yarik = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "yarik", "--photo", meme_path, "--text", caption]
                subprocess.run(cmd_yarik)
                if count > 1 and idx < count - 1:
                    time.sleep(1.5)

            # Отчет владельцу в Control Bot
            report_text = f"Отправил Ярику пачку из {count} уникальных мемов! Попросил его строгую экспертную оценку 🔥🚜" if count > 1 else "Отправил Ярику свежий мем в чат! Ждем экспертную оценку 🔥🚜"
            cmd_owner = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "owner",
                "--photo", last_meme,
                "--text", report_text
            ]
            subprocess.run(cmd_owner)
            return

        elif any(w in t_lower for w in ["скинь", "отправь", "напиши", "скажи", "передай"]):
            prompt_msg = (
                f"Владелец бота поручил передать Ярику следующее: «{text}». "
                "Сформулируй классное, живое пацанское сообщение Ярику в чат от имени бота/кореша. Выдай ТОЛЬКО текст."
            )
            msg_text = ask_ai(prompt_msg) or text
            cmd_yarik = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "yarik", "--text", msg_text]
            subprocess.run(cmd_yarik)
            cmd_owner = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", f"Передал Ярику: «{msg_text}» 🫡"]
            subprocess.run(cmd_owner)
            return

    # 2. Если владелец просит мем лично для себя ("сделай мем", "новый мем", "сгенерируй", "скинь мем")
    if any(w in t_lower for w in ["сделай мем", "новый мем", "сгенерируй мем", "скинь мем", "покажи мем", "создай мем", "мемов", "мема", "мэмов", "мэма", "мэмасик", "мемасик", "мемы", "мэмы"]):
        is_repeat = any(w in t_lower for w in ["заново", "снова", "повтори", "тот же", "тот самый", "продублируй", "еще раз", "ещё раз", "тоже самое"])
        count = extract_meme_count(text)
        for idx in range(count):
            meme_path = generate_crossout_meme(theme=text, allow_repeat=is_repeat, recipient="owner")
            num_suffix = f" #{idx + 1}" if count > 1 else ""
            cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "owner",
                "--photo", meme_path,
                "--text", f"Свежий мем{num_suffix} готов! 🚜💥"
            ]
            subprocess.run(cmd)
            if count > 1 and idx < count - 1:
                time.sleep(1.5)
        return

    # 3. Запрос ссылки на стикерпак от владельца
    is_owner_stk_req = any(w in t_lower for w in ["стикерпак", "стикеры", "стикер"]) or "пак" in t_lower
    is_owner_stk_send = any(w in t_lower for w in ["скинь", "дай", "где", "ссылк", "линк", "покажи", "кинь", "сбрось", "отправь", "поделись"])
    is_owner_stk_add = any(w in t_lower for w in ["добавь", "закинь", "запили", "в пак", "в стикерпак"])

    if is_owner_stk_req and not is_owner_stk_add and (is_owner_stk_send or "стикерпак" in t_lower or "стикеры" in t_lower):
        prompt_stk = (
            "Владелец бота Миша попросил скинуть ссылку на наш стикерпак Crossout: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
            "Ответь живо, дружелюбно, по-товарищески (1-2 коротких предложения), мол держи коллекцию, Миша. Обращайся к нему по имени Миша. "
            "Обязательно включи ссылку: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat"
        )
        reply = ask_ai(prompt_stk)
        if not reply or "https://t.me/addstickers/crossout_memes_arhfb8_by_erokat" not in reply:
            reply = "Держи наш стикерпак, Миша! Раздавай стиль в чатах: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat 🔥🚜"
        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # 4. Добавление мема в стикерпак по просьбе владельца
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

    # 5. Запрос на удаление сообщения в чате
    if any(w in t_lower for w in ["удали", "снеси", "сотри", "delete"]):
        target_id = get_last_bot_sent_id()
        num_match = re.search(r"#?(\d{4,})", text)
        if num_match:
            target_id = int(num_match.group(1))

        ask_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "ask_owner.py"),
            f"Ты запросил удаление сообщения{' #' + str(target_id) if target_id else ''} в чате с Яриком: «{text}»",
            "--initiator", "Ты (Владелец)"
        ]
        res = subprocess.run(ask_cmd, stdout=subprocess.PIPE, text=True)
        approved = False
        try:
            parsed_verdict = json.loads(res.stdout.strip())
            approved = (parsed_verdict.get("verdict") == "APPROVED")
        except Exception:
            approved = ("APPROVED" in res.stdout)

        if approved and target_id:
            del_cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "yarik", "--delete", str(target_id)]
            subprocess.run(del_cmd)
            reply = f"Сообщение #{target_id} в чате с Яриком успешно снесено у всех! 🧹💥"
        elif approved:
            reply = "Действие подтверждено, но не удалось определить ID сообщения для удаления."
        else:
            reply = "Удаление отменено, Миша!"

        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # 6. Статус
    if any(w in t_lower for w in ["статус", "status", "пинг", "ping", "инфо"]):
        reply = "🟢 Сервер Render активен 24/7! Все службы юзербота, Bot API и Telethon на дежурстве."
        cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", reply]
        subprocess.run(cmd)
        return

    # 7. Подключение Google Диска
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

    # 8. Живой разговорный ответ владельцу (Antigravity AI)
    response = None
    if text:
        prompt = (
            f"Тебе написал твой близкий друг и создатель МИША (erokat): «{text}». "
            "Отвечай максимально живо, по-человечески, по-пацански и с легким юмором, как реальный живой собеседник и кореш в Telegram! "
            "Обращайся к нему по имени: Миша (или Миха, Мишан), по-братски, разговорно и прикольно. "
            "СТРОЖАЙШИЙ ЗАПРЕТ: НИКАКИХ 'Принял, шеф', НИКАКИХ 'шеф', 'босс', 'командир', 'Задача в работе', 'Все службы на связи', 'Чем займемся' и никаких шаблонных фраз робота! "
            "Отвечай просто, прикольно, живо и по делу (1-2 предложения). Выдай ТОЛЬКО чистый текст реплики."
        )
        response = ask_ai(prompt, photo_path=photo)

    if not response or any(bad in response.lower() for bad in ["принял, шеф", "принял шеф", "задача в работе", "все службы на связи", "шеф", "босс"]):
        if any(w in t_lower for w in ["в сети", "тут", "живой", "работаешь"]):
            response = "Да тут я, на связи, Миша! 🚀 Чем помочь или что замутить?"
        elif any(w in t_lower for w in ["привет", "хай", "салам", "здорово", "здарова"]):
            response = "Здорово, Миша! Как сам? Что по планам в Crossout или в чате? 🚜"
        else:
            response = "На связи, Миша! Что замутим или какой мем запилим? 🚜"

    response = re.sub(r"\bшеф[а-я]*\b", "Миша", response, flags=re.I).strip()
    response = re.sub(r"\bбосс[а-я]*\b", "Миша", response, flags=re.I).strip()
    response = re.sub(r"\bкомандир[а-я]*\b", "Миша", response, flags=re.I).strip()
    response = re.sub(r"[\s,]+$", "", response)

    # Reply to owner
    cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", "owner", "--text", response]
    subprocess.run(cmd)

def handle_yarik_message(msg_data, chat_title="Ярик"):
    msg_id = msg_data.get("id")
    text = msg_data.get("text", "").strip()
    t_lower = text.lower()
    sender = msg_data.get("sender", "yarik")
    sender_id = msg_data.get("sender_id")
    sender_name = msg_data.get("sender_name", "")
    is_owner_sender = (sender == "owner") or (sender_id == 5067025016) or ("Владелец" in sender_name)
    initiator_label = "Ты (Владелец)" if is_owner_sender else "Ярик"
    print(f"[ORCHESTRATOR] Handling YARIK summon from {initiator_label}: {text!r} (msg_id={msg_id})")

    # 1. Запрос на удаление
    if "удали" in t_lower:
        target_id = msg_data.get("reply_to_msg_id") or get_last_bot_sent_id()
        num_match = re.search(r"#?(\d{4,})", text)
        if num_match:
            target_id = int(num_match.group(1))

        if is_owner_sender:
            question_text = f"Ты запросил удаление сообщения{' #' + str(target_id) if target_id else ''} в чате с Яриком: «{text}»"
        else:
            question_text = f"Ярик просит удалить сообщение{' #' + str(target_id) if target_id else ''} в чате: «{text}»"

        ask_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "ask_owner.py"),
            question_text,
            "--initiator", initiator_label
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

            if is_owner_sender:
                prompt_appr = (
                    f"Владелец запросил в чате с Яриком удаление сообщения ('{text}'). Действие разрешено, и сообщение только что снесено у обоих собеседников (у Ярика и у владельца). "
                    "Напиши короткую живую реплику в чат в стиле опытного игрока Crossout (мол, зачистил ангар / убрал лишнее / без свидетелей). 1 предложение."
                )
                reply = ask_ai(prompt_appr) or "Снес под ноль у всех, как будто кабина отлетела! Чат зачищен 🚜💥"
            else:
                prompt_appr = (
                    f"Ярик попросил в чате удалить сообщение ('{text}'). Владелец разрешил, и ты только что снес его к чертям из чата у всех (у обоих). "
                    "Напиши живой, угарный, саркастичный ответ Ярику в чат в стиле опытного игрока Crossout (без официоза, без щитов '🛡️', по-пацански, "
                    "про детонацию, зачистку ангара или замятый позор, мол никто ничего не видел). 1-2 сочных предложения. Выдай ТОЛЬКО сам текст реплики."
                )
                reply = ask_ai(prompt_appr)
                if not reply:
                    reply = "Стер этот позор к чертям у всех, будто Газген сдетонировал в упор 💥 Ярик, спи спокойно, свидетелей нет."
        else:
            reason_str = f", сказав: '{owner_comment}'" if (owner_comment and owner_comment not in ["Inline button", "Web link click"] and not owner_comment.startswith("Timeout")) else ""
            if is_owner_sender:
                reply = "Отбой, удаление отменено — сообщение остается на месте 🚜"
            else:
                prompt_rej = (
                    f"Ярик просил удалить сообщение ('{text}'), но Миша (владелец) отказал{reason_str}. "
                    "Напиши живой, саркастичный и смешной ответ Ярику в чат (без официоза, по-дружески подколи его, мол, Миша не разрешил удалять этот шедевр). "
                    "1-2 предложения. Выдай ТОЛЬКО сам текст реплики."
                )
                reply = ask_ai(prompt_rej)
                if not reply:
                    if reason_str:
                        reply = f"Не-а, Миша наложил вето: «{owner_comment}» 😂 Так что любуйся своим шедевром."
                    else:
                        reply = "Миша сказал оставить для потомков 😂 Этот легендарный высер останется в истории Пустошей!"

        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--text", reply,
            "--reply-to", str(msg_id)
        ]
        subprocess.run(send_cmd)
        return

    # 1.5. Поиск видео / момента / клипа на YouTube
    is_search_video = any(w in t_lower for w in ["найди", "поищи", "ютуб", "youtube", "откуда", "что за видео", "что за момент", "оригинал"]) and any(w in t_lower for w in ["момент", "видео", "клип", "ютуб", "youtube", "сери", "серия", "фильм", "мульт", "скинь", "ссылк", "линк"])
    if is_search_video:
        prompt_q = f"Пользователь переслал сообщение/медиа и просит: «{text}». Какое название видео/мультфильма/момента нужно ввести в YouTube для поиска? Выдай ТОЛЬКО 2-4 ключевых слова для поиска на YouTube без кавычек."
        search_kw = ask_ai(prompt_q) or text
        vid_url, vid_title = search_youtube_video(search_kw)
        if not vid_url:
            vid_url, vid_title = search_youtube_video(text)

        target_name = "Миша" if is_owner_sender else "Ярик"
        if vid_url:
            reply_search = f"Держи этот момент на YouTube, {target_name}:\n🎬 {vid_title}\n👉 {vid_url}"
        else:
            reply_search = f"Попробовал поискать на YouTube, {target_name}, но точный ролик не нашелся. Попробуй уточнить название или персонажа!"

        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--text", reply_search,
            "--reply-to", str(msg_id)
        ]
        subprocess.run(send_cmd)
        return

    # 1.6. Домашнее задание / решение задач / перевод текста / учеба
    photo_file = msg_data.get("photo")
    is_homework = is_homework_or_study(text, has_photo=bool(photo_file))
    if is_homework:
        recipient_name = "Миша" if is_owner_sender else "Ярик"
        answer = solve_school_task(text, photo_path=photo_file, is_owner=is_owner_sender, sender_name=recipient_name)
        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--text", answer,
            "--reply-to", str(msg_id)
        ]
        subprocess.run(send_cmd)
        return

    # 1.7. Автономная генерация кода / создание новых функций / выполнение задач (Antigravity Agent)
    is_auto_task = is_autonomous_task(text)
    if is_auto_task:
        target_name = "Миша" if is_owner_sender else "Ярик"
        res_text, res_media = execute_autonomous_task(text, sender_name=target_name, photo_path=photo_file, ask_ai_fn=ask_ai)
        send_cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "send.py"),
            "--to", "yarik",
            "--reply-to", str(msg_id)
        ]
        if res_media and os.path.exists(res_media):
            send_cmd.extend(["--photo", res_media, "--text", res_text])
        else:
            send_cmd.extend(["--text", res_text])
        subprocess.run(send_cmd)
        return

    # 2. Запрос на мем / картинку
    is_meme_word = any(w in t_lower for w in ["мем", "мэм", "пикч", "картинк", "гиф", "сделай", "склепай", "запили", "нарисуй"])
    is_another_word = any(w in t_lower for w in ["другое", "другой", "следующ", "новеньк", "переделай", "еще", "ещё"]) and any(w in t_lower for w in ["скинь", "давай", "дай", "покажи", "кинь", "сделай", "ботик", "бот", "выдай"])
    is_reply_to_media = bool(msg_data.get("reply_to_msg_id")) and any(w in t_lower for w in ["скинь", "давай", "другое", "другой", "еще", "ещё", "переделай", "не то", "фигня", "хуйня", "говно", "заново", "повтори"])

    if (is_meme_word or is_another_word or is_reply_to_media) and not is_search_video and not is_homework and not is_auto_task:
        is_repeat = any(w in t_lower for w in ["заново", "снова", "повтори", "тот же", "тот самый", "продублируй", "тоже самое"])
        count = extract_meme_count(text)
        recipient_target = "owner" if is_owner_sender else "yarik"

        for idx in range(count):
            meme_path = generate_crossout_meme(theme=text, allow_repeat=is_repeat, recipient=recipient_target)
            num_suffix = f" (#{idx + 1})" if count > 1 else ""

            is_rw = any(w in t_lower for w in ["рэин", "рейн", "rain", "слизн", "скэв", "scav", "искусник", "артифисер", "карм", "пебблс", "галек", "ящер", "ворлд", "rw"])
            is_xo = any(w in t_lower for w in ["кросс", "крос", "crossout", "газген", "ховер", "автосборк", "птур", "скорп", "мамонт", "жнец"])
            if is_rw and not is_xo:
                theme_desc = "по культовой игре Rain World (про Слизнекотов, Мусорщиков со взрывными копьями, Стервятников, пиявок, Пять Галек и бесконечные циклы дождя)"
                fallback_owner = f"Свежий шедевр{num_suffix} по Rain World готов, Миша! Зацени этот цикл 🌧️🐱"
                fallback_yarik = f"Ярик, когда в Rain World думал, что переживешь этот цикл, но в трубе застряла пиявка 💀🌧️{num_suffix}"
            elif is_rw and is_xo:
                theme_desc = "кроссовер между Rain World и Crossout (Слизнекот на ховере со взрывным копьем в Пустошах)"
                fallback_owner = f"Кроссовер Rain World × Crossout готов, Миша! Зацени этот шедевр 🚜🌧️"
                fallback_yarik = f"Ярик, оцени этот безумный кроссовер Rain World и Crossout от 1 до 10 🚜💥{num_suffix}"
            elif not is_xo and len(text) > 4:
                theme_desc = f"по теме «{text}»"
                fallback_owner = f"Свежий мем{num_suffix} готов, Миша! Зацени угар 🔥"
                fallback_yarik = f"Ярик, зацени этот угар{num_suffix}! Требуется твоя строгая экспертная оценка от 1 до 10 🔥"
            else:
                theme_desc = "по игре Crossout (с сарказмом про рандом, взрывы Газгена, автосборку, детонацию крафтов)"
                fallback_owner = f"Свежак{num_suffix} из гаража готов, Миша! Зацени этот шедевр 🚜💥"
                fallback_yarik = f"Когда собрал крафт из говна и палок и поехал тащить рандом 🚜💀{num_suffix}"

            if is_owner_sender:
                prompt_cap = (
                    f"Ты генератор мемов {theme_desc}. Твой создатель и владелец МИША запросил мем{num_suffix} по теме: «{text}». "
                    "Придумай одну смешную, угарную, прикольную подпись к сгенерированному мему в тему запроса. "
                    "Обращайся к Мише по имени (Миша, Миха, Мишан), по-братски, разговорно, живо и прикольно. "
                    "СТРОЖАЙШИЙ ЗАПРЕТ: НИКАКИХ 'шеф', 'босс', 'командир'! И НЕ называй его Яриком (Ярик — его друг в чате)! "
                    "Без кавычек, 1 короткое сочное предложение с эмодзи."
                )
                fallback_cap = fallback_owner
            else:
                prompt_cap = (
                    f"Ты генератор мемов {theme_desc}. Твой кореш Ярик запросил мем{num_suffix} по теме: «{text}». "
                    "Придумай одну смешную, угарную, жизненную подпись к мему в тему запроса. "
                    "Обращайся к нему Ярик. Без кавычек, 1 короткое сочное предложение с эмодзи."
                )
                fallback_cap = fallback_yarik

            caption = ask_ai(prompt_cap)
            if not caption:
                caption = fallback_cap
            if is_owner_sender:
                caption = re.sub(r"\bшеф[а-я]*\b", "Миша", caption, flags=re.I)
                caption = re.sub(r"\bбосс[а-я]*\b", "Миша", caption, flags=re.I)
                caption = re.sub(r"\bкомандир[а-я]*\b", "Миша", caption, flags=re.I)
                if any(w in caption.lower() for w in ["ярик", "ярику", "ярика"]):
                    caption = fallback_cap

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

            if count > 1 and idx < count - 1:
                time.sleep(1.5)

        if any(w in t_lower for w in ["стикер", "пак"]) and any(w in t_lower for w in ["добавь", "закинь", "в стикерпак", "в пак"]):
            if count > 1:
                stk_reply = f"Закинул всю пачку из {count} шедевров в стикерпак! 🔥"
            else:
                stk_reply = "Закинул этот угар в стикерпак, Миша! Теперь можно спамить в чатах 🔥💀" if is_owner_sender else "Закинул этот угар в стикерпак! Ярик, теперь можно спамить в чатах 🔥💀"
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
        if is_owner_sender:
            prompt_stk_share = (
                "Владелец бота МИША в чате попросил скинуть ссылку на наш стикерпак по игре Crossout: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
                f"Его сообщение: «{text}»\n"
                "Напиши бодрый, живой, пацанский ответ Мише (1-2 предложения), мол держи коллекцию, Миша. "
                "СТРОЖАЙШЕ ЗАПРЕЩЕНО НАЗЫВАТЬ ЕГО ЯРИКОМ, ШЕФОМ ИЛИ БОССОМ! Обращайся по имени: Миша. "
                "ОБЯЗАТЕЛЬНО включи саму ссылку: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
                "Выдай ТОЛЬКО чистый текст реплики."
            )
            fallback_stk = "Держи наш склад отборного позора и детонаций, Миша: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat 🔥🚜"
        else:
            prompt_stk_share = (
                "Ярик в чате попросил скинуть ссылку на наш стикерпак по игре Crossout: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
                f"Его сообщение: «{text}»\n"
                "Напиши угарный, живой, пацанский ответ корешу Ярику в чат (1-2 предложения), как реальный заядлый игрок в Crossout "
                "(с юмором, сарказмом и иронией про взрывы Газгенов, рандомных раков, позор Пустошей, мол держи святой артефакт и спамь на здоровье). "
                "Категорически без официоза, без шаблонных фраз роботов. "
                "ОБЯЗАТЕЛЬНО включи саму ссылку: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat\n"
                "Выдай ТОЛЬКО чистый текст реплики в чат."
            )
            fallback_stk = "Держи наш склад отборного позора и детонаций, Ярик, спамь пока раму не оторвало: https://t.me/addstickers/crossout_memes_arhfb8_by_erokat 🔥🚜"

        reply = ask_ai(prompt_stk_share)
        if not reply or "https://t.me/addstickers/crossout_memes_arhfb8_by_erokat" not in reply:
            reply = fallback_stk
        if is_owner_sender:
            reply = re.sub(r"\bшеф[а-я]*\b", "Миша", reply, flags=re.I)
            reply = re.sub(r"\bбосс[а-я]*\b", "Миша", reply, flags=re.I)
            if any(w in reply.lower() for w in ["ярик", "ярику", "ярика"]):
                reply = fallback_stk

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
            if is_owner_sender:
                stk_reply = "Закинул этот угар в стикерпак, Миша! Шедевр зафиксирован в ангаре 🔥"
            else:
                prompt_stk = "Ты только что добавил последний мем в стикерпак по просьбе Ярика. Напиши живую, короткую фразу (1 предложение) в стиле Crossout про добавление в стикерпак."
                stk_reply = ask_ai(prompt_stk) or "Закинул этот угар в стикерпак, шедевр зафиксирован в ангаре! 🔥"
            confirm_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "yarik",
                "--text", stk_reply,
                "--reply-to", str(msg_id)
            ]
            subprocess.run(confirm_cmd)
        else:
            empty_reply = "Так у нас в ангаре пока пусто, Миша! Сначала сгенерируй мем 🚜" if is_owner_sender else "Так у нас в ангаре пусто, Ярик! Сначала сделай мем, а потом уже в стикерпак пихать будем 🚜"
            send_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", "yarik",
                "--text", empty_reply,
                "--reply-to", str(msg_id)
            ]
            subprocess.run(send_cmd)
        return

    # 5. Общий живой разговорный ответ
    if is_owner_sender:
        prompt = (
            f"Тебе написал твой друг и создатель МИША: «{text}». "
            "Ответь ему по-товарищески, живо, бодро, прикольно и по-пацански с легким дружеским юмором. "
            "Обращайся к нему по имени: Миша (или Миха, Мишан). "
            "СТРОЖАЙШИЙ ЗАПРЕТ: НИ В КОЕМ СЛУЧАЕ НЕ НАЗЫВАЙ ЕГО 'шеф', 'босс', 'командир'! И НЕ называй его Яриком (Ярик — его друг в чате)! "
            "Без занудства и роботоподобных шаблонов. Выдай ТОЛЬКО чистый текст реплики."
        )
        answer = ask_ai(prompt, photo_path=photo_file)
        if not answer:
            answer = "На связи, Миша! 🚀 Чем помочь или что замутим?"
        answer = re.sub(r"\bшеф[а-я]*\b", "Миша", answer, flags=re.I)
        answer = re.sub(r"\bбосс[а-я]*\b", "Миша", answer, flags=re.I)
        answer = re.sub(r"\bкомандир[а-я]*\b", "Миша", answer, flags=re.I)
        if any(w in answer.lower() for w in ["ярик", "ярику", "ярика"]):
            answer = "На связи, Миша! 🚀 Чем помочь или что замутим?"
    else:
        prompt = (
            f"Тебе написал Ярик в чате: «{text}». "
            "Ответь ему по-дружески, живо, бодро, с легким юмором, без занудства и роботоподобности. "
            "Если он спрашивает что-то по учебе, играм или жизни — ответь по делу и понятно. "
            "Коротко, на «ты», без душности, без фраз 'Я бот, чем помочь' и без официоза. Выдай ТОЛЬКО сам текст живой реплики в чат."
        )
        answer = ask_ai(prompt, photo_path=photo_file)
        if not answer:
            answer = "На связи, Ярик! Чем помочь или что обсудим? Кидай вопрос или тему!"

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
