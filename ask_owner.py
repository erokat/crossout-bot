import os
import sys
import json
import time
import uuid
import re
import argparse
import urllib.request
import urllib.parse


from config import load_config
from db import (
    init_db,
    create_confirmation,
    update_confirmation_message_id,
    resolve_confirmation,
    get_confirmation,
    get_kv,
    set_kv
)

def send_bot_message(bot_token, chat_id, text, reply_markup=None):
    if not bot_token:
        return None
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    clean_text = str(text).strip()
    if len(clean_text) > 4096:
        clean_text = clean_text[:4090] + "..."
    payload = {
        "chat_id": chat_id,
        "text": clean_text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        # If HTML parse error (400), retry without parse_mode
        try:
            payload.pop("parse_mode", None)
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as retry_e:
            sys.stderr.write(f"Failed to send bot message fallback: {retry_e}\n")
            return None
    except Exception as e:
        sys.stderr.write(f"Failed to send bot message: {e}\n")
        return None

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

def answer_callback(bot_token, callback_query_id, text=""):
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    try:
        payload = {"callback_query_id": callback_query_id, "text": text}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def remove_inline_keyboard(bot_token, chat_id, message_id):
    if not bot_token or not chat_id or not message_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup"
    payload = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "reply_markup": {"inline_keyboard": []}
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        sys.stderr.write(f"Failed to edit message reply markup {message_id}: {e}\n")
        return False


def main():
    parser = argparse.ArgumentParser(description="Запрос подтверждения у владельца")
    parser.add_argument("question", help="Текст вопроса / действия")
    parser.add_argument("--initiator", default=None, help="Кто запрашивает действие (Ярик или Ты (Владелец))")
    args = parser.parse_args()

    question = args.question.strip()
    initiator = args.initiator

    if not initiator:
        q_lower = question.lower()
        if "ярик" in q_lower:
            initiator = "Ярик"
        elif any(w in q_lower for w in ["ты ", "владелец", "миша", "шеф", "owner"]):
            initiator = "Ты (Миша)"
        else:
            initiator = "Ярик"

    init_db()
    cfg = load_config()

    bot_token = cfg["bot_token"]
    owner_id = cfg["owner_id"]
    render_url = cfg["render_url"] or "https://yarik-crossout-userbot.onrender.com"

    req_id = uuid.uuid4().hex[:8]
    approve_link = f"{render_url}/confirm?id={req_id}&action=approve"
    reject_link = f"{render_url}/confirm?id={req_id}&action=reject"

    msg_text = (
        f"<b>⚠️ ТРЕБУЕТСЯ ВАШЕ ПОДТВЕРЖДЕНИЕ ⚠️</b>\n\n"
        f"👤 <b>Кто просит:</b> {initiator}\n"
        f"❓ <b>Действие:</b>\n{question}\n\n"
        f"<b>Ссылки для быстрого ответа:</b>\n"
        f"✅ <a href=\"{approve_link}\">Разрешить действие</a>\n"
        f"❌ <a href=\"{reject_link}\">Отклонить действие</a>\n\n"
        f"<i>(Или выберите кнопку ниже либо напишите ответ прямо в этот чат)</i>"
    )

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Разрешить", "callback_data": f"approve_{req_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{req_id}"}
            ]
        ]
    }

    sent_res = send_bot_message(bot_token, owner_id, msg_text, reply_markup=inline_keyboard)
    prompt_msg_id = None
    if sent_res and sent_res.get("ok"):
        prompt_msg_id = sent_res["result"]["message_id"]

    create_confirmation(req_id, question, message_id=prompt_msg_id, initiator=initiator)

    offset_str = get_kv("control_bot_offset", "0")
    try:
        current_offset = int(offset_str)
    except Exception:
        current_offset = 0

    if current_offset == 0 and bot_token:
        try:
            url_init = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1&timeout=2"
            req_init = urllib.request.Request(url_init, headers={"User-Agent": "CrossoutBot/1.0"})
            with urllib.request.urlopen(req_init, timeout=4) as r_init:
                d_init = json.loads(r_init.read().decode("utf-8"))
                if d_init.get("ok") and d_init.get("result"):
                    current_offset = d_init["result"][-1]["update_id"] + 1
                    set_kv("control_bot_offset", str(current_offset))
        except Exception:
            pass

    timeout = 180
    start_time = time.time()
    verdict = None
    comment = ""

    while time.time() - start_time < timeout:
        # 1. Check SQLite database for resolution (from Web endpoint, inline buttons, or owner reply)
        conf = get_confirmation(req_id)
        if conf and conf.get("status") in ["approved", "rejected"]:
            verdict = conf["status"].upper()
            comment = conf.get("comment") or ""
            if prompt_msg_id:
                remove_inline_keyboard(bot_token, owner_id, prompt_msg_id)
            break

        # 2. Direct getUpdates polling from Telegram Bot API
        if bot_token:
            try:
                poll_url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={current_offset}&timeout=2"
                poll_req = urllib.request.Request(poll_url, headers={"User-Agent": "CrossoutBot/1.0"})
                with urllib.request.urlopen(poll_req, timeout=4) as p_resp:
                    upd_data = json.loads(p_resp.read().decode("utf-8"))

                if upd_data.get("ok"):
                    updates = upd_data.get("result", [])
                    for upd in updates:
                        upd_id = upd.get("update_id", 0)

                        # Check callback query
                        cq = upd.get("callback_query")
                        if cq:
                            cq_id = cq.get("id")
                            cq_data = cq.get("data", "")
                            from_uid = cq.get("from", {}).get("id")
                            is_owner = (owner_id is None) or (from_uid == owner_id) or (str(from_uid) == str(owner_id))
                            if is_owner and cq_data in [f"approve_{req_id}", f"reject_{req_id}"]:
                                action = "approved" if cq_data.startswith("approve_") else "rejected"
                                verdict = action.upper()
                                comment = "Inline button"
                                resolve_confirmation(req_id, action, comment=comment)
                                answer_callback(bot_token, cq_id, f"{'✅ Разрешено' if action == 'approved' else '❌ Отклонено'}!")
                                if prompt_msg_id:
                                    remove_inline_keyboard(bot_token, owner_id, prompt_msg_id)
                                current_offset = upd_id + 1
                                set_kv("control_bot_offset", str(current_offset))
                                try:
                                    ack_url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={current_offset}&limit=1"
                                    urllib.request.urlopen(urllib.request.Request(ack_url, headers={"User-Agent": "CrossoutBot/1.0"}), timeout=3)
                                except Exception:
                                    pass
                                break

                        # Check incoming owner message (text replies like "да", "+", "нет", "-")
                        msg = upd.get("message")
                        if msg:
                            from_uid = msg.get("from", {}).get("id")
                            is_owner = (owner_id is None) or (from_uid == owner_id) or (str(from_uid) == str(owner_id))
                            msg_text = (msg.get("text") or msg.get("caption") or "").strip()
                            if is_owner and msg_text:
                                t_lower = msg_text.lower()
                                reply_to = msg.get("reply_to_message", {})
                                is_reply_to_prompt = bool(reply_to and prompt_msg_id and reply_to.get("message_id") == prompt_msg_id)
                                is_rejection = bool(re.search(r"(?:\b(?:нет|отказ[а-я]*|нельзя|отмен[а-я]*|отбой|reject)\b|(?<!\S)-(?!\S))", t_lower) or re.search(r"\bне\s+(?:удаляй|надо|трогай|делай|разрешай)", t_lower))
                                is_approval = bool(not is_rejection and re.search(r"(?:\b(?:да|разреш[а-я]*|ок|удаляй|сноси|подтвержд[а-я]*|yes)\b|(?<!\S)\+(?!\S))", t_lower))

                                if is_approval or is_rejection:
                                    action = "rejected" if is_rejection else "approved"
                                    verdict = action.upper()
                                    comment = f"Текст владельца: {msg_text}"
                                    resolve_confirmation(req_id, action, comment=comment)
                                    mid = msg.get("message_id")
                                    if mid:
                                        try:
                                            from db import add_handled_id, mark_message_handled
                                            add_handled_id(mid, owner_id)
                                            mark_message_handled(mid, owner_id)
                                        except Exception:
                                            pass
                                    if prompt_msg_id:
                                        remove_inline_keyboard(bot_token, owner_id, prompt_msg_id)
                                    current_offset = upd_id + 1
                                    set_kv("control_bot_offset", str(current_offset))
                                    try:
                                        ack_url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={current_offset}&limit=1"
                                        urllib.request.urlopen(urllib.request.Request(ack_url, headers={"User-Agent": "CrossoutBot/1.0"}), timeout=3)
                                    except Exception:
                                        pass
                                    break
            except Exception:
                pass

        if verdict:
            break

        time.sleep(0.5)

    if not verdict:
        verdict = "REJECTED"
        comment = "Timeout 180s"
        resolve_confirmation(req_id, "rejected", comment)
        if prompt_msg_id:
            remove_inline_keyboard(bot_token, owner_id, prompt_msg_id)
        send_bot_message(bot_token, owner_id, f"⏳ Время ожидания ответа истекло (таймаут {timeout}с). Действие отклонено по умолчанию.")
    else:
        status_symbol = "✅" if verdict == "APPROVED" else "❌"
        status_word = "разрешен" if verdict == "APPROVED" else "отклонен"
        target_name = "Ярика" if "ярик" in initiator.lower() else "тебя"
        res_text = f"{status_symbol} <b>Запрос на удаление от {target_name} {status_word}!</b>"
        if comment and comment not in ["Inline button", "Web link click"]:
            res_text += f"\n<i>Комментарий: {comment}</i>"
        send_bot_message(bot_token, owner_id, res_text)


    print(json.dumps({
        "req_id": req_id,
        "verdict": verdict,
        "comment": comment
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
