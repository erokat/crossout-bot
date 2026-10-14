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
from db import init_db, save_message, save_chat, get_kv, set_kv

def is_bot_mention(text):
    if not text:
        return False
    t = text.lower().strip()
    triggers = ["!бот", "!bot", "/бот", "/bot", "бот ответь", "бот,", "ботяра", "ботик", "робот"]
    if any(tr in t for tr in triggers):
        return True
    if re.search(r"\bбот\b", t):
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

                # Check if it's an incoming message from the owner
                msg = upd.get("message")
                if not msg:
                    continue
                
                from_user = msg.get("from", {})
                from_id = from_user.get("id")
                
                if from_id == owner_id:
                    msg_id = msg.get("message_id")
                    text = msg.get("text") or msg.get("caption") or ""
                    date_str = str(msg.get("date", int(time.time())))

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
                            "sender": "owner"
                        }]
                    }
                    exit_event.set()
                    return

        except Exception as e:
            # sys.stderr.write(f"Bot polling error: {e}\n")
            await asyncio.sleep(2)

async def main():
    parser = argparse.ArgumentParser(description="Ожидание сообщений от Ярика и владельца")
    parser.add_argument("--after-id", type=int, default=None, help="ID последнего известного сообщения Ярика")
    parser.add_argument("--timeout", type=int, default=900, help="Таймаут ожидания в секундах")
    parser.add_argument("--filter-mentions", action="store_true", default=True, help="Реагировать только на обращения")
    args = parser.parse_args()

    init_db()
    cfg = load_config()
    yarik_chat_id = cfg["yarik_chat_id"]

    exit_event = asyncio.Event()
    result_box = {}

    # Start Bot API listener task for Owner
    bot_task = asyncio.create_task(poll_control_bot(cfg, exit_event, result_box))

    # Initialize Telethon client for Yarik
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

                after_id = args.after_id
                if after_id is None:
                    last_msgs = await client.get_messages(entity, limit=1)
                    after_id = last_msgs[0].id if last_msgs else 0

                bot_sent = get_bot_sent_ids()

                # Check recent unhandled messages
                async for m in client.iter_messages(entity, min_id=after_id):
                    if m.id in bot_sent:
                        continue
                    is_from_yarik = (m.sender_id == yarik_chat_id)
                    is_mention = is_bot_mention(m.message)

                    if not is_mention:
                        if is_from_yarik:
                            save_message(
                                chat_id=yarik_chat_id,
                                message_id=m.id,
                                chat_title=chat_title,
                                sender_id=m.sender_id,
                                sender_name=chat_title,
                                date=m.date.isoformat(),
                                text=m.message or "",
                                has_media=1 if m.photo else 0,
                                media_type="photo" if m.photo else None,
                                media_path=None
                            )
                        continue

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

                    save_message(
                        chat_id=yarik_chat_id,
                        message_id=m.id,
                        chat_title=chat_title,
                        sender_id=m.sender_id,
                        sender_name=chat_title if is_from_yarik else "Me",
                        date=m.date.isoformat(),
                        text=m.message or "",
                        has_media=has_media,
                        media_type=media_type,
                        media_path=media_path
                    )

                    reply_to_id = getattr(m, "reply_to_msg_id", None) or (m.reply_to.reply_to_msg_id if getattr(m, "reply_to", None) else None)
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
                            "sender": "yarik" if is_from_yarik else "owner"
                        }]
                    }
                    exit_event.set()
                    break

                @client.on(events.NewMessage(chats=yarik_chat_id))
                async def on_new_message(event):
                    msg = event.message
                    bot_sent = get_bot_sent_ids()
                    if msg.id in bot_sent:
                        return

                    is_from_yarik = (msg.sender_id == yarik_chat_id)
                    is_mention = is_bot_mention(msg.message)

                    if not is_mention:
                        if is_from_yarik:
                            save_message(
                                chat_id=yarik_chat_id,
                                message_id=msg.id,
                                chat_title=chat_title,
                                sender_id=msg.sender_id,
                                sender_name=chat_title,
                                date=msg.date.isoformat(),
                                text=msg.message or "",
                                has_media=1 if msg.photo else 0,
                                media_type="photo" if msg.photo else None,
                                media_path=None
                            )
                        return

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

                    save_message(
                        chat_id=yarik_chat_id,
                        message_id=msg.id,
                        chat_title=chat_title,
                        sender_id=msg.sender_id,
                        sender_name=chat_title if is_from_yarik else "Me",
                        date=msg.date.isoformat(),
                        text=msg.message or "",
                        has_media=has_media,
                        media_type=media_type,
                        media_path=media_path
                    )

                    reply_to_id = getattr(msg, "reply_to_msg_id", None) or (msg.reply_to.reply_to_msg_id if getattr(msg, "reply_to", None) else None)
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
                            "sender": "yarik" if is_from_yarik else "owner"
                        }]
                    }
                    exit_event.set()

            except Exception as e:
                sys.stderr.write(f"Telethon entity error: {e}\n")

        # Wait for either Telethon or Bot API to trigger, or timeout
        try:
            await asyncio.wait_for(exit_event.wait(), timeout=args.timeout)
            print(json.dumps(result_box.get("data", {}), ensure_ascii=False))
        except asyncio.TimeoutError:
            print(json.dumps({"status": "timeout"}))

    finally:
        bot_task.cancel()
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
