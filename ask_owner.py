import os
import sys
import json
import time
import uuid
import urllib.request
import urllib.parse

from config import load_config
from db import init_db, create_confirmation, resolve_confirmation, get_confirmation, get_kv, set_kv

def send_bot_message(bot_token, chat_id, text, reply_markup=None):
    if not bot_token:
        return None
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write(f"Failed to send bot message: {e}\n")
        return None

def answer_callback(bot_token, callback_query_id, text=""):
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    try:
        payload = {"callback_query_id": callback_query_id, "text": text}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 ask_owner.py \"<Question text>\"\n")
        sys.exit(1)

    question = sys.argv[1].strip()
    init_db()
    cfg = load_config()

    bot_token = cfg["bot_token"]
    owner_id = cfg["owner_id"]
    render_url = cfg["render_url"] or "https://yarik-crossout-userbot.onrender.com"

    req_id = uuid.uuid4().hex[:8]
    create_confirmation(req_id, question)

    approve_link = f"{render_url}/confirm?id={req_id}&action=approve"
    reject_link = f"{render_url}/confirm?id={req_id}&action=reject"

    msg_text = (
        f"<b>⚠️ ТРЕБУЕТСЯ ВАШЕ ПОДТВЕРЖДЕНИЕ ⚠️</b>\n\n"
        f"<b>Вопрос:</b>\n{question}\n\n"
        f"<b>Ссылки для быстрого ответа:</b>\n"
        f"✅ <a href=\"{approve_link}\">Разрешить действие</a>\n"
        f"❌ <a href=\"{reject_link}\">Отклонить действие</a>\n\n"
        f"<i>(Или нажмите кнопку ниже либо напишите ответ прямо в этот чат)</i>"
    )

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Разрешить", "callback_data": f"approve_{req_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{req_id}"}
            ]
        ]
    }

    send_bot_message(bot_token, owner_id, msg_text, reply_markup=inline_keyboard)

    timeout = 180
    start_time = time.time()
    offset_str = get_kv("control_bot_offset", "0")
    try:
        offset = int(offset_str)
    except ValueError:
        offset = 0

    verdict = None
    comment = ""

    while time.time() - start_time < timeout:
        # 1. Check SQLite database (in case confirmed via Web HTTP endpoint)
        conf = get_confirmation(req_id)
        if conf and conf["status"] in ["approved", "rejected"]:
            verdict = conf["status"].upper()
            comment = conf.get("comment") or "Web link click"
            break

        # 2. Check Bot API updates for callback query or text message
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=2"
            req = urllib.request.Request(url, headers={"User-Agent": "CrossoutBot/1.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
            
            if data.get("ok"):
                for upd in data.get("result", []):
                    upd_id = upd["update_id"]
                    offset = max(offset, upd_id + 1)
                    set_kv("control_bot_offset", str(offset))

                    # Check callback queries
                    cb = upd.get("callback_query")
                    if cb:
                        cb_data = cb.get("data", "")
                        if cb_data == f"approve_{req_id}":
                            answer_callback(bot_token, cb["id"], "✅ Разрешено!")
                            verdict = "APPROVED"
                            comment = "Inline button"
                            resolve_confirmation(req_id, "approved", comment)
                            break
                        elif cb_data == f"reject_{req_id}":
                            answer_callback(bot_token, cb["id"], "❌ Отклонено!")
                            verdict = "REJECTED"
                            comment = "Inline button"
                            resolve_confirmation(req_id, "rejected", comment)
                            break

                    # Check text messages from owner
                    msg = upd.get("message")
                    if msg and msg.get("from", {}).get("id") == owner_id:
                        text = (msg.get("text") or "").strip()
                        t_lower = text.lower()
                        if any(w in t_lower for w in ["да", "разреш", "ок", "удаляй", "yes", "подтвержд"]):
                            verdict = "APPROVED"
                            comment = text
                            resolve_confirmation(req_id, "approved", comment)
                            break
                        elif any(w in t_lower for w in ["нет", "отказ", "не ", "нельзя", "отмен", "no"]):
                            verdict = "REJECTED"
                            comment = text
                            resolve_confirmation(req_id, "rejected", comment)
                            break
                        else:
                            verdict = "APPROVED" if "не" not in t_lower else "REJECTED"
                            comment = text
                            resolve_confirmation(req_id, verdict.lower(), comment)
                            break
        except Exception:
            pass

        if verdict:
            break

        time.sleep(1.5)

    if not verdict:
        verdict = "REJECTED"
        comment = "Timeout 180s"
        resolve_confirmation(req_id, "rejected", comment)
        send_bot_message(bot_token, owner_id, f"⏳ Время ожидания ответа истекло (таймаут {timeout}с). Действие отклонено по умолчанию.")
    else:
        status_symbol = "✅" if verdict == "APPROVED" else "❌"
        status_word = "Разрешено" if verdict == "APPROVED" else "Отклонено"
        send_bot_message(bot_token, owner_id, f"{status_symbol} <b>Действие {status_word}!</b>\n<i>Комментарий: {comment}</i>")

    print(json.dumps({
        "req_id": req_id,
        "verdict": verdict,
        "comment": comment
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
