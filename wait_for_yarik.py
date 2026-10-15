import os
import sys
import json
import time
import asyncio
import argparse
import re
import urllib.request
import urllib.parse
from telethon import TelegramClient, events
from telethon.tl.types import User

from config import (
    load_config,
    SESSION_PATH,
    MEDIA_DIR,
    BOT_SENT_FILE,
    LOCK_PATH
)
import fcntl
from db import (
    init_db,
    save_message,
    save_chat,
    get_kv,
    set_kv,
    is_message_handled,
    mark_message_handled,
    is_handled,
    add_handled_id as db_add_handled_id,
    configure_session_sqlite,
    session_flock,
    resolve_confirmation,
    get_latest_pending_confirmation
)

def is_bot_mention(text):
    if not text:
        return False
    t = text.lower().strip()
    triggers = ["!бот", "!bot", "/бот", "/bot", "бот ответь", "бот,", "ботяра", "ботик", "робот", "стикерпак", "стикеры"]
    if any(tr in t for tr in triggers):
        return True
    if re.search(r"\bбот\b", t):
        return True
    if re.search(r"х+у+е+с+о+с+", t):
        return True
    if any(m in t for m in ["музык", "трек", "песн", "гиф", "gif", "видос", "видео"]) and any(a in t for a in ["скинь", "найди", "скачай", "включи", "поставь", "сгенерируй"]):
        return True
    return False


def get_bot_sent_ids():
    if not os.path.exists(BOT_SENT_FILE):
        return set()
    try:
        with open(BOT_SENT_FILE, "r") as f:
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except Exception:
        return set()

HANDLED_MSGS_FILE = os.path.join(os.path.dirname(BOT_SENT_FILE), "handled_msg_ids.txt")

def get_handled_ids(target_chat_id=None):
    ids = set()
    if os.path.exists(HANDLED_MSGS_FILE):
        try:
            with open(HANDLED_MSGS_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if ":" in line:
                        parts = line.split(":", 1)
                        if parts[0].lstrip("-").isdigit() and parts[1].isdigit():
                            cid, mid = int(parts[0]), int(parts[1])
                            if target_chat_id is None or cid == int(target_chat_id) or cid == 0:
                                ids.add(mid)
                    elif line.isdigit():
                        ids.add(int(line))
        except Exception:
            pass
    return ids

def add_handled_id(msg_id, chat_id=0):
    try:
        cid = int(chat_id) if chat_id is not None else 0
        with open(HANDLED_MSGS_FILE, "a") as f:
            f.write(f"{cid}:{msg_id}\n")
    except Exception:
        pass
    db_add_handled_id(msg_id, chat_id)


async def download_bot_file(bot_token, file_id, dest_path):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            return None
        file_path = data["result"]["file_path"]
        dl_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        dl_req = urllib.request.Request(dl_url, headers={"User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(dl_req, timeout=30) as dl_resp:
            content = dl_resp.read()
        with open(dest_path, "wb") as f:
            f.write(content)
        return dest_path
    except Exception as e:
        sys.stderr.write(f"Failed to download bot file: {e}\n")
        return None

async def poll_control_bot(cfg, exit_event, result_box):
    bot_token = cfg.get("bot_token")
    owner_id = cfg.get("owner_id")
    if not bot_token or not owner_id:
        return

    offset_str = get_kv("control_bot_offset", "0")
    try:
        offset = int(offset_str)
    except ValueError:
        offset = 0

    if offset == 0:
        try:
            url_init = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1&timeout=2"
            req_init = urllib.request.Request(url_init, headers={"User-Agent": "CrossoutBot/1.0"})
            with urllib.request.urlopen(req_init, timeout=5) as r_init:
                d_init = json.loads(r_init.read().decode("utf-8"))
                if d_init.get("ok") and d_init.get("result"):
                    offset = d_init["result"][-1]["update_id"] + 1
                    set_kv("control_bot_offset", str(offset))
        except Exception:
            pass

    while not exit_event.is_set():
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=5"
            req = urllib.request.Request(url, headers={"User-Agent": "CrossoutBot/1.0"})
            
            # Run blocking HTTP request in executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            resp_bytes = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10).read())
            data = json.loads(resp_bytes.decode("utf-8"))
            
            if not data.get("ok"):
                await asyncio.sleep(2)
                continue

            updates = data.get("result", [])
            for upd in updates:
                upd_id = upd["update_id"]
                offset = max(offset, upd_id + 1)
                set_kv("control_bot_offset", str(offset))

                # 1. Check callback queries from inline buttons (for confirmation approval/rejection)
                cq = upd.get("callback_query")
                if cq:
                    cq_id = cq.get("id")
                    cq_data = cq.get("data", "")
                    cq_from_id = cq.get("from", {}).get("id")
                    if cq_from_id == owner_id and (cq_data.startswith("approve_") or cq_data.startswith("reject_")):
                        action, target_id = cq_data.split("_", 1)
                        status = "approved" if action == "approve" else "rejected"
                        resolve_confirmation(target_id, status, comment="Inline button")
                        try:
                            url_ans = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                            pld = json.dumps({"callback_query_id": cq_id, "text": f"{'✅ Разрешено' if status == 'approved' else '❌ Отклонено'}!"}).encode("utf-8")
                            req_ans = urllib.request.Request(url_ans, data=pld, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
                            await loop.run_in_executor(None, lambda: urllib.request.urlopen(req_ans, timeout=5))
                        except Exception:
                            pass
                        cq_msg = cq.get("message", {})
                        cq_msg_id = cq_msg.get("message_id")
                        if cq_msg_id:
                            try:
                                url_del = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
                                pld_del = json.dumps({"chat_id": owner_id, "message_id": int(cq_msg_id)}).encode("utf-8")
                                req_del = urllib.request.Request(url_del, data=pld_del, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
                                await loop.run_in_executor(None, lambda: urllib.request.urlopen(req_del, timeout=5))
                            except Exception:
                                pass
                        continue

                # 2. Check if it's an incoming message from the owner
                msg = upd.get("message")
                if not msg:
                    continue
                
                from_user = msg.get("from", {})
                from_id = from_user.get("id")
                
                if from_id == owner_id:
                    msg_id = msg.get("message_id")
                    if is_handled(msg_id, owner_id) or is_message_handled(msg_id, owner_id) or msg_id in get_handled_ids(owner_id):
                        continue
                    add_handled_id(msg_id, owner_id)
                    text = msg.get("text") or msg.get("caption") or ""
                    date_str = str(msg.get("date", int(time.time())))

                    # Check if this message resolves an active pending confirmation (within 180s timeout)
                    pending_conf = get_latest_pending_confirmation()
                    if pending_conf and text and (time.time() - float(pending_conf.get("created_at") or 0) <= 180):
                        t_lower = text.strip().lower()
                        reply_to = msg.get("reply_to_message", {})
                        is_reply_to_prompt = bool(reply_to and pending_conf.get("message_id") and reply_to.get("message_id") == pending_conf.get("message_id"))
                        is_rejection = bool(re.search(r"(?:\b(?:нет|отказ[а-я]*|нельзя|отмен[а-я]*|отбой|reject)\b|(?<!\S)-(?!\S))", t_lower) or re.search(r"\bне\s+(?:удаляй|надо|трогай|делай|разрешай)", t_lower))
                        is_approval = bool(not is_rejection and re.search(r"(?:\b(?:да|разреш[а-я]*|ок|удаляй|сноси|подтвержд[а-я]*|yes)\b|(?<!\S)\+(?!\S))", t_lower))

                        if is_reply_to_prompt or is_approval or is_rejection:
                            status = "rejected" if is_rejection else ("approved" if (is_approval or is_reply_to_prompt) else "rejected")
                            resolve_confirmation(pending_conf["req_id"], status, comment=f"Текст владельца: {text}")
                            p_msg_id = pending_conf.get("message_id")
                            if p_msg_id:
                                try:
                                    url_del = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
                                    pld_del = json.dumps({"chat_id": owner_id, "message_id": int(p_msg_id)}).encode("utf-8")
                                    req_del = urllib.request.Request(url_del, data=pld_del, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
                                    await loop.run_in_executor(None, lambda: urllib.request.urlopen(req_del, timeout=5))
                                except Exception:
                                    pass
                            continue

                    media_path = None
                    has_media = 0
                    media_type = None
                    if "video" in msg and msg["video"]:
                        has_media = 1
                        media_type = "video"
                        vid = msg["video"]
                        dest = os.path.join(MEDIA_DIR, f"owner_{msg_id}.mp4")
                        media_path = await download_bot_file(bot_token, vid["file_id"], dest)
                    elif "animation" in msg and msg["animation"]:
                        has_media = 1
                        media_type = "video"
                        anim = msg["animation"]
                        dest = os.path.join(MEDIA_DIR, f"owner_{msg_id}.mp4")
                        media_path = await download_bot_file(bot_token, anim["file_id"], dest)
                    elif "photo" in msg and msg["photo"]:
                        has_media = 1
                        media_type = "photo"
                        largest_photo = msg["photo"][-1]
                        dest = os.path.join(MEDIA_DIR, f"owner_{msg_id}.jpg")
                        media_path = await download_bot_file(bot_token, largest_photo["file_id"], dest)
                    elif "document" in msg and msg["document"]:
                        has_media = 1
                        doc = msg["document"]
                        fname = doc.get("file_name", f"doc_{msg_id}.bin")
                        dest = os.path.join(MEDIA_DIR, f"owner_{msg_id}_{fname}")
                        media_path = await download_bot_file(bot_token, doc["file_id"], dest)
                        media_type = "video" if fname.lower().endswith((".mp4", ".mov", ".avi", ".webm")) else "document"

                    reply_msg = msg.get("reply_to_message")
                    reply_to_id = reply_msg.get("message_id") if reply_msg else None
                    if not media_path and reply_msg:
                        if "photo" in reply_msg and reply_msg["photo"]:
                            has_media = 1
                            media_type = "photo"
                            largest_photo = reply_msg["photo"][-1]
                            dest = os.path.join(MEDIA_DIR, f"owner_reply_{reply_to_id}.jpg")
                            media_path = await download_bot_file(bot_token, largest_photo["file_id"], dest)
                        elif "video" in reply_msg and reply_msg["video"]:
                            has_media = 1
                            media_type = "video"
                            vid = reply_msg["video"]
                            dest = os.path.join(MEDIA_DIR, f"owner_reply_{reply_to_id}.mp4")
                            media_path = await download_bot_file(bot_token, vid["file_id"], dest)
                        elif "animation" in reply_msg and reply_msg["animation"]:
                            has_media = 1
                            media_type = "video"
                            anim = reply_msg["animation"]
                            dest = os.path.join(MEDIA_DIR, f"owner_reply_{reply_to_id}.mp4")
                            media_path = await download_bot_file(bot_token, anim["file_id"], dest)
                        elif "document" in reply_msg and reply_msg["document"]:
                            doc = reply_msg["document"]
                            fname = doc.get("file_name", f"doc_{reply_to_id}.bin")
                            dest = os.path.join(MEDIA_DIR, f"owner_reply_{reply_to_id}_{fname}")
                            dl_path = await download_bot_file(bot_token, doc["file_id"], dest)
                            if dl_path:
                                media_path = dl_path
                                if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                                    has_media = 1
                                    media_type = "photo"
                                elif fname.lower().endswith((".mp4", ".mov", ".avi", ".webm")):
                                    has_media = 1
                                    media_type = "video"

                    save_message(
                        chat_id=owner_id,
                        message_id=msg_id,
                        chat_title="Owner Chat",
                        sender_id=owner_id,
                        sender_name=from_user.get("first_name", "Owner"),
                        date=date_str,
                        text=text,
                        has_media=has_media,
                        media_type=media_type,
                        media_path=media_path
                    )

                    result_box["data"] = {
                        "status": "new_messages",
                        "source": "owner",
                        "chat_id": owner_id,
                        "messages": [{
                            "id": msg_id,
                            "date": date_str,
                            "text": text,
                            "photo": media_path,
                            "video": media_path if media_type == "video" else None,
                            "media_type": media_type,
                            "reply_to_msg_id": reply_to_id,
                            "sender": "owner"
                        }]
                    }
                    exit_event.set()
                    return

        except Exception as e:
            # sys.stderr.write(f"Bot polling error: {e}\n")
            await asyncio.sleep(2)

async def download_reply_media(client, entity, msg, yarik_chat_id):
    media_path = None
    media_type = None
    has_media = 0
    reply_to_id = None
    try:
        replied_m = None
        if hasattr(msg, "get_reply_message"):
            try:
                replied_m = await msg.get_reply_message()
            except Exception:
                pass

        reply_to_id = getattr(msg, "reply_to_msg_id", None) or (msg.reply_to.reply_to_msg_id if getattr(msg, "reply_to", None) else None)
        if not replied_m and reply_to_id and client and entity:
            try:
                replied_m = await client.get_messages(entity, ids=reply_to_id)
            except Exception:
                pass

        if replied_m:
            if not reply_to_id:
                reply_to_id = replied_m.id

            is_img = replied_m.photo or (replied_m.document and getattr(replied_m.document, "mime_type", "").startswith("image/")) or (hasattr(replied_m, 'file') and getattr(replied_m.file, 'ext', '').lower() in ['.jpg', '.jpeg', '.png', '.webp'])
            is_vid = replied_m.video or (replied_m.document and getattr(replied_m.document, "mime_type", "").startswith("video/")) or (hasattr(replied_m, 'file') and getattr(replied_m.file, 'ext', '').lower() in ['.mp4', '.mov', '.webm', '.avi'])

            if is_img:
                has_media = 1
                media_type = "photo"
                dest = os.path.join(MEDIA_DIR, f"{yarik_chat_id}_{replied_m.id}.jpg")
                if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                    dl = await replied_m.download_media(file=dest)
                    if dl and os.path.exists(dl) and os.path.getsize(dl) > 0:
                        media_path = dl
                else:
                    media_path = dest
            elif is_vid:
                has_media = 1
                media_type = "video"
                dest = os.path.join(MEDIA_DIR, f"{yarik_chat_id}_{replied_m.id}.mp4")
                if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                    dl = await replied_m.download_media(file=dest)
                    if dl and os.path.exists(dl) and os.path.getsize(dl) > 0:
                        media_path = dl
                else:
                    media_path = dest
            elif replied_m.media:
                try:
                    dl = await replied_m.download_media(file=MEDIA_DIR)
                    if dl and os.path.exists(dl) and os.path.getsize(dl) > 0:
                        has_media = 1
                        ext = os.path.splitext(dl)[1].lower()
                        media_type = "video" if ext in ['.mp4', '.mov', '.webm', '.avi'] else "photo"
                        media_path = dl
                except Exception:
                    pass
    except Exception as e:
        sys.stderr.write(f"[WAIT_FOR_YARIK] Error in download_reply_media: {e}\n")
    return media_path, media_type, has_media, reply_to_id

async def main():
    parser = argparse.ArgumentParser(description="Ожидание сообщений от Ярика и владельца")
    parser.add_argument("--after-id", type=int, default=None, help="ID последнего известного сообщения Ярика")
    parser.add_argument("--timeout", type=int, default=900, help="Таймаут ожидания в секундах")
    parser.add_argument("--filter-mentions", action="store_true", default=True, help="Реагировать только на обращения")
    parser.add_argument("--get-latest-id", action="store_true", default=False, help="Получить ID последнего сообщения чата и выйти")
    args = parser.parse_args()

    init_db()
    cfg = load_config()

    if args.get_latest_id:
        configure_session_sqlite()
        client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
        await client.connect()
        try:
            if not await client.is_user_authorized():
                print(json.dumps({"latest_id": 0}))
                return
            entity = await client.get_entity(cfg["yarik_chat_id"])
            latest_msgs = await client.get_messages(entity, limit=1)
            lid = latest_msgs[0].id if latest_msgs else 0
            print(json.dumps({"latest_id": lid}))
            return
        except Exception as e:
            sys.stderr.write(f"Error getting latest id: {e}\n")
            print(json.dumps({"latest_id": 0}))
            return
        finally:
            await client.disconnect()

    yarik_chat_id = cfg["yarik_chat_id"]
    owner_id = cfg.get("owner_id", 5067025016)

    exit_event = asyncio.Event()
    result_box = {}

    # Start Bot API listener task for Owner
    bot_task = asyncio.create_task(poll_control_bot(cfg, exit_event, result_box))
    poll_messages_task = None

    # Initialize Telethon client for Yarik
    configure_session_sqlite()
    client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
    await client.connect()

    if not await client.is_user_authorized():
        # Telethon session not authorized; let bot_task run if possible or error
        sys.stderr.write("Warning: Telethon session not authorized.\n")

    try:
        if await client.is_user_authorized():
            try:
                entity = await client.get_entity(yarik_chat_id)
                chat_title = getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Ярик')
                save_chat(yarik_chat_id, chat_title, getattr(entity, 'username', None), "private")

                bot_sent = get_bot_sent_ids()
                handled_ids = get_handled_ids()
                after_id = args.after_id
                if after_id is None:
                    # DO NOT process past messages from 600 seconds ago!
                    # Fetch current newest message ID and ONLY wait for genuinely NEW messages!
                    latest_msgs = await client.get_messages(entity, limit=1)
                    if latest_msgs:
                        after_id = latest_msgs[0].id
                    check_stream = client.iter_messages(entity, min_id=after_id) if after_id else client.iter_messages(entity, limit=0)
                else:
                    check_stream = client.iter_messages(entity, min_id=after_id)

                # Check recent unhandled messages
                async for m in check_stream:
                    if m.id in bot_sent or m.id in handled_ids or is_handled(m.id, yarik_chat_id) or is_message_handled(m.id, yarik_chat_id):
                        continue
                    if after_id is not None and m.id <= after_id:
                        continue

                    sender_uid = m.sender_id or (getattr(m.from_id, 'user_id', None) if getattr(m, 'from_id', None) else None)
                    is_owner = getattr(m, 'out', False) or (sender_uid == owner_id) or (sender_uid is not None and sender_uid != yarik_chat_id)
                    is_from_yarik = not is_owner
                    is_mention = is_bot_mention(m.message)

                    if not is_mention:
                        add_handled_id(m.id, yarik_chat_id)
                        mark_message_handled(m.id, yarik_chat_id)
                        if is_from_yarik:
                            save_message(
                                chat_id=yarik_chat_id,
                                message_id=m.id,
                                chat_title=chat_title,
                                sender_id=sender_uid,
                                sender_name=chat_title,
                                date=m.date.isoformat(),
                                text=m.message or "",
                                has_media=1 if m.photo else 0,
                                media_type="photo" if m.photo else None,
                                media_path=None
                            )
                        continue

                    add_handled_id(m.id, yarik_chat_id)

                    # Triggered by mention
                    media_path = None
                    has_media = 0
                    media_type = None
                    if m.video:
                        has_media = 1
                        media_type = "video"
                        media_path = os.path.join(MEDIA_DIR, f"{yarik_chat_id}_{m.id}.mp4")
                        if not os.path.exists(media_path):
                            await m.download_media(file=media_path)
                    elif m.photo:
                        has_media = 1
                        media_type = "photo"
                        media_path = os.path.join(MEDIA_DIR, f"{yarik_chat_id}_{m.id}.jpg")
                        if not os.path.exists(media_path):
                            await m.download_media(file=media_path)
                    elif m.media:
                        try:
                            dl_path = await m.download_media(file=MEDIA_DIR)
                            if dl_path:
                                has_media = 1
                                media_path = dl_path
                                media_type = "video" if dl_path.lower().endswith((".mp4", ".mov", ".avi", ".webm")) else "photo"
                        except Exception:
                            pass

                    sender_label = "Ты (Владелец)" if is_owner else "Ярик"
                    sender_key = "owner" if is_owner else "yarik"
                    save_message(
                        chat_id=yarik_chat_id,
                        message_id=m.id,
                        chat_title=chat_title,
                        sender_id=sender_uid,
                        sender_name=sender_label,
                        date=m.date.isoformat(),
                        text=m.message or "",
                        has_media=has_media,
                        media_type=media_type,
                        media_path=media_path
                    )

                    reply_to_id = getattr(m, "reply_to_msg_id", None) or (m.reply_to.reply_to_msg_id if getattr(m, "reply_to", None) else None)
                    if not media_path:
                        r_path, r_type, r_has, r_id = await download_reply_media(client, entity, m, yarik_chat_id)
                        if r_path:
                            media_path = r_path
                            media_type = r_type
                            has_media = r_has
                        if r_id and not reply_to_id:
                            reply_to_id = r_id

                    result_box["data"] = {
                        "status": "new_messages",
                        "source": "yarik",
                        "chat_id": yarik_chat_id,
                        "chat_title": chat_title,
                        "messages": [{
                            "id": m.id,
                            "date": m.date.isoformat(),
                            "text": m.message or "",
                            "photo": media_path,
                            "video": media_path if media_type == "video" else None,
                            "media_type": media_type,
                            "reply_to_msg_id": reply_to_id,
                            "is_mention": True,
                            "sender": sender_key,
                            "sender_id": sender_uid,
                            "sender_name": sender_label
                        }]
                    }
                    exit_event.set()
                    break

                async def handle_candidate_message(msg):
                    if exit_event.is_set():
                        return
                    if msg.id in get_bot_sent_ids() or msg.id in get_handled_ids() or is_handled(msg.id, yarik_chat_id) or is_message_handled(msg.id, yarik_chat_id):
                        return
                    if after_id is not None and msg.id <= after_id:
                        return

                    sender_uid = msg.sender_id or (getattr(msg.from_id, 'user_id', None) if getattr(msg, 'from_id', None) else None)
                    is_owner = getattr(msg, 'out', False) or (sender_uid == owner_id) or (sender_uid is not None and sender_uid != yarik_chat_id)
                    is_from_yarik = not is_owner
                    is_mention = is_bot_mention(msg.message)

                    if not is_mention:
                        add_handled_id(msg.id, yarik_chat_id)
                        mark_message_handled(msg.id, yarik_chat_id)
                        if is_from_yarik:
                            save_message(
                                chat_id=yarik_chat_id,
                                message_id=msg.id,
                                chat_title=chat_title,
                                sender_id=sender_uid,
                                sender_name=chat_title,
                                date=msg.date.isoformat(),
                                text=msg.message or "",
                                has_media=1 if msg.photo else 0,
                                media_type="photo" if msg.photo else None,
                                media_path=None
                            )
                        return

                    add_handled_id(msg.id, yarik_chat_id)

                    media_path = None
                    has_media = 0
                    media_type = None
                    if msg.video:
                        has_media = 1
                        media_type = "video"
                        media_path = os.path.join(MEDIA_DIR, f"{yarik_chat_id}_{msg.id}.mp4")
                        try:
                            await msg.download_media(file=media_path)
                        except Exception:
                            pass
                    elif msg.photo:
                        has_media = 1
                        media_type = "photo"
                        media_path = os.path.join(MEDIA_DIR, f"{yarik_chat_id}_{msg.id}.jpg")
                        try:
                            await msg.download_media(file=media_path)
                        except Exception:
                            pass
                    elif msg.media:
                        try:
                            dl_path = await msg.download_media(file=MEDIA_DIR)
                            if dl_path:
                                has_media = 1
                                media_path = dl_path
                                media_type = "video" if dl_path.lower().endswith((".mp4", ".mov", ".avi", ".webm")) else "photo"
                        except Exception:
                            pass

                    sender_label = "Ты (Владелец)" if is_owner else "Ярик"
                    sender_key = "owner" if is_owner else "yarik"
                    save_message(
                        chat_id=yarik_chat_id,
                        message_id=msg.id,
                        chat_title=chat_title,
                        sender_id=sender_uid,
                        sender_name=sender_label,
                        date=msg.date.isoformat(),
                        text=msg.message or "",
                        has_media=has_media,
                        media_type=media_type,
                        media_path=media_path
                    )

                    reply_to_id = getattr(msg, "reply_to_msg_id", None) or (msg.reply_to.reply_to_msg_id if getattr(msg, "reply_to", None) else None)
                    if not media_path:
                        r_path, r_type, r_has, r_id = await download_reply_media(client, entity, msg, yarik_chat_id)
                        if r_path:
                            media_path = r_path
                            media_type = r_type
                            has_media = r_has
                        if r_id and not reply_to_id:
                            reply_to_id = r_id

                    result_box["data"] = {
                        "status": "new_messages",
                        "source": "yarik",
                        "chat_id": yarik_chat_id,
                        "chat_title": chat_title,
                        "messages": [{
                            "id": msg.id,
                            "date": msg.date.isoformat(),
                            "text": msg.message or "",
                            "photo": media_path,
                            "video": media_path if media_type == "video" else None,
                            "media_type": media_type,
                            "reply_to_msg_id": reply_to_id,
                            "is_mention": True,
                            "sender": sender_key,
                            "sender_id": sender_uid,
                            "sender_name": sender_label
                        }]
                    }
                    exit_event.set()

                @client.on(events.NewMessage(chats=yarik_chat_id))
                async def on_new_message(event):
                    await handle_candidate_message(event.message)

                # Periodic polling of chat messages to catch outgoing messages from owner (UpdateShortSentMessage)
                async def poll_recent_telethon_messages():
                    while not exit_event.is_set():
                        try:
                            recent = await client.get_messages(entity, limit=4)
                            for rm in recent:
                                if rm.id in get_bot_sent_ids() or rm.id in get_handled_ids() or is_handled(rm.id, yarik_chat_id) or is_message_handled(rm.id, yarik_chat_id):
                                    continue
                                if after_id is not None and rm.id <= after_id:
                                    continue
                                if is_bot_mention(rm.message):
                                    await handle_candidate_message(rm)
                                    return
                        except Exception:
                            pass
                        await asyncio.sleep(3)

                poll_messages_task = asyncio.create_task(poll_recent_telethon_messages())

            except Exception as e:
                sys.stderr.write(f"Telethon entity error: {e}\n")

        # Wait for either Telethon or Bot API to trigger, or timeout
        try:
            await asyncio.wait_for(exit_event.wait(), timeout=args.timeout)
            print(json.dumps(result_box.get("data", {}), ensure_ascii=False))
        except asyncio.TimeoutError:
            print(json.dumps({"status": "timeout", "latest_id": after_id}))

    finally:
        bot_task.cancel()
        if poll_messages_task:
            poll_messages_task.cancel()
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())

