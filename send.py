import os
import sys
import shutil
import argparse
import asyncio
import fcntl
import uuid
import json
import urllib.request
import urllib.parse
from telethon import TelegramClient

from config import (
    load_config,
    SESSION_PATH,
    SAVED_MEMES_DIR,
    LOCK_PATH,
    BOT_SENT_FILE
)

def make_multipart_body(fields, files):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        if value is not None:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.extend(f"{value}\r\n".encode("utf-8"))
    for name, (filename, content, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return body, f"multipart/form-data; boundary={boundary}"

def send_via_bot_api(bot_token, chat_id, text=None, file_path=None, reply_to=None):
    if not bot_token:
        sys.stderr.write("Error: CONTROL_BOT_TOKEN is not set\n")
        return None

    try:
        if file_path and os.path.exists(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in [".gif"]:
                endpoint = "sendAnimation"
                file_field = "animation"
                mime_type = "image/gif"
            elif ext in [".mp4", ".mov", ".mkv", ".webm"]:
                endpoint = "sendVideo"
                file_field = "video"
                mime_type = "video/mp4"
            elif ext in [".mp3", ".ogg", ".wav", ".m4a", ".flac"]:
                endpoint = "sendAudio"
                file_field = "audio"
                mime_type = "audio/mpeg"
            else:
                endpoint = "sendPhoto"
                file_field = "photo"
                mime_type = "image/png"
            url = f"https://api.telegram.org/bot{bot_token}/{endpoint}"

            
            with open(file_path, "rb") as f:
                content = f.read()

            fields = {"chat_id": chat_id}
            if text:
                fields["caption"] = text
            if reply_to:
                fields["reply_to_message_id"] = reply_to

            files = {file_field: (os.path.basename(file_path), content, mime_type)}
            body, ctype = make_multipart_body(fields, files)

            req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype, "User-Agent": "CrossoutBot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                return res_json

        elif text:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            if reply_to:
                payload["reply_to_message_id"] = reply_to
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))

    except Exception as e:
        sys.stderr.write(f"Bot API send error: {e}\n")
        return None

def delete_via_bot_api(bot_token, chat_id, message_id):
    if not bot_token:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
    try:
        payload = json.dumps({"chat_id": chat_id, "message_id": message_id}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "CrossoutBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("ok", False)
    except Exception as e:
        sys.stderr.write(f"Bot API delete error: {e}\n")
        return False

async def delete_via_telethon(cfg, chat_id, message_ids):
    lock_file = open(LOCK_PATH, "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

    client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
    await client.connect()

    if not await client.is_user_authorized():
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        sys.stderr.write("Error: Telethon session not authorized\n")
        sys.exit(1)

    try:
        entity = await client.get_entity(chat_id)
        await client.delete_messages(entity, message_ids, revoke=True)
        print(f"Telethon deleted messages {message_ids} in chat {chat_id} (revoke=True for everyone)")
        return True
    finally:
        await client.disconnect()
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

async def send_via_telethon(cfg, chat_id, text=None, photo_path=None, reply_to=None):
    lock_file = open(LOCK_PATH, "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

    client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
    await client.connect()

    if not await client.is_user_authorized():
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        sys.stderr.write("Error: Telethon session not authorized\n")
        sys.exit(1)

    try:
        entity = await client.get_entity(chat_id)
        msg = None
        if photo_path:
            if not os.path.exists(photo_path):
                sys.stderr.write(f"Error: Photo path not found: {photo_path}\n")
                sys.exit(1)

            # 1. Save local copy into SAVED_MEMES_DIR
            os.makedirs(SAVED_MEMES_DIR, exist_ok=True)
            dest_file = os.path.join(SAVED_MEMES_DIR, os.path.basename(photo_path))
            if os.path.abspath(photo_path) != os.path.abspath(dest_file):
                shutil.copy2(photo_path, dest_file)
            print(f"Meme copy saved: {dest_file}")

            # 1. Send to chat (Yarik) via Telethon
            msg = await client.send_file(
                entity,
                photo_path,
                caption=text or "",
                reply_to=reply_to
            )
            print(f"Telethon file sent (msg_id={msg.id})")

            # 2. Automatically forward a copy to Owner via Control Bot
            if cfg.get("bot_token") and cfg.get("owner_id"):
                caption = f"🚀 Копия отправленного Ярику медиа:\n{text or ''}".strip()
                send_via_bot_api(
                    cfg["bot_token"],
                    cfg["owner_id"],
                    text=caption,
                    file_path=photo_path
                )

            # 3. Upload to Google Drive and clean up local storage
            try:
                from gdrive import upload_and_cleanup
                ext = os.path.splitext(photo_path)[1].lower()
                if ext in [".mp3", ".ogg", ".wav", ".m4a", ".flac"]:
                    folder_type = "music"
                elif ext in [".mp4", ".mov", ".mkv", ".webm", ".avi", ".gif"]:
                    folder_type = "videos"
                else:
                    folder_type = "memes"

                upload_and_cleanup(photo_path, folder_type=folder_type)
                if dest_file != photo_path and os.path.exists(dest_file):
                    try:
                        os.remove(dest_file)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[GDRIVE UPLOAD WARNING] {e}")

        else:
            msg = await client.send_message(
                entity,
                text,
                reply_to=reply_to
            )
            print(f"Telethon text sent (msg_id={msg.id})")

        if msg:
            with open(BOT_SENT_FILE, "a") as f:
                f.write(f"{msg.id}\n")

    finally:
        await client.disconnect()
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

def main():
    parser = argparse.ArgumentParser(description="Отправка сообщений в Telegram (Bot API или Telethon)")
    parser.add_argument("--to", choices=["owner", "yarik"], default=None, help="Получатель: owner или yarik")
    parser.add_argument("--chat", type=int, default=None, help="Прямой ID чата")
    parser.add_argument("--text", type=str, default=None, help="Текст сообщения")
    parser.add_argument("--photo", type=str, default=None, help="Путь к фото или анимации")
    parser.add_argument("--reply-to", type=int, default=None, help="ID сообщения для ответа")
    parser.add_argument("--delete", type=int, nargs="+", default=None, help="ID сообщений для удаления")
    args = parser.parse_args()

    if not args.text and not args.photo and not args.delete:
        sys.stderr.write("Error: --text, --photo, or --delete must be specified\n")
        sys.exit(1)

    cfg = load_config()

    target = args.to
    if not target:
        if args.chat == cfg["owner_id"]:
            target = "owner"
        else:
            target = "yarik"

    if args.delete:
        if target == "owner":
            for mid in args.delete:
                res = delete_via_bot_api(cfg["bot_token"], cfg["owner_id"], mid)
                print(f"Deleted message {mid} for owner via Bot API: {res}")
        else:
            chat_id = args.chat or cfg["yarik_chat_id"]
            asyncio.run(delete_via_telethon(cfg, chat_id, args.delete))
        return

    if target == "owner":
        res = send_via_bot_api(
            bot_token=cfg["bot_token"],
            chat_id=cfg["owner_id"],
            text=args.text,
            file_path=args.photo,
            reply_to=args.reply_to
        )
        print("Sent to owner via Bot API:", res.get("ok") if res else False)
    else:
        chat_id = args.chat or cfg["yarik_chat_id"]
        asyncio.run(send_via_telethon(
            cfg=cfg,
            chat_id=chat_id,
            text=args.text,
            photo_path=args.photo,
            reply_to=args.reply_to
        ))

if __name__ == "__main__":
    main()
