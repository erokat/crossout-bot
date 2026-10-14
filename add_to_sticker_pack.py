import os
import sys
import asyncio
import random
import argparse
import fcntl
from PIL import Image
from telethon import TelegramClient

from config import load_config, SESSION_PATH, MEDIA_DIR, LOCK_PATH

PACK_SHORT_NAME = "crossout_memes_arhfb8_by_erokat"
EMOJIS = ["💥", "💀", "🚗", "🤖", "🔥", "😂", "🚀", "💣", "🚜", "🗿", "⚡", "🎮", "😼", "🎯", "🛡️"]

def prepare_sticker(img_path):
    im = Image.open(img_path).convert('RGBA')
    w, h = im.size
    if w > h:
        new_w = 512
        new_h = int(h * (512 / w))
    else:
        new_h = 512
        new_w = int(w * (512 / h))
    im_resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
    tmp_path = os.path.join(MEDIA_DIR, f"tmp_sticker_{os.getpid()}.png")
    im_resized.save(tmp_path, "PNG", optimize=True)
    return tmp_path

async def main():
    parser = argparse.ArgumentParser(description="Добавить мем в стикерпак")
    parser.add_argument("--image", required=True, help="Путь к изображению мема")
    parser.add_argument("--emoji", default=None, help="Эмодзи для стикера")
    args = parser.parse_args()

    if not os.path.exists(args.image):
        sys.stderr.write(f"Error: image not found {args.image}\n")
        sys.exit(1)

    sticker_file = prepare_sticker(args.image)
    emoji = args.emoji or random.choice(EMOJIS)

    lock_file = open(LOCK_PATH, "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

    cfg = load_config()
    client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
    await client.connect()

    if not await client.is_user_authorized():
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        sys.stderr.write("Error: Telethon session not authorized\n")
        sys.exit(1)

    try:
        stickers_bot = await client.get_entity("Stickers")
        await client.send_message(stickers_bot, "/cancel")
        await asyncio.sleep(1.5)

        await client.send_message(stickers_bot, "/addsticker")
        await asyncio.sleep(1.5)

        await client.send_message(stickers_bot, PACK_SHORT_NAME)
        await asyncio.sleep(2)

        await client.send_file(stickers_bot, sticker_file, force_document=True)
        await asyncio.sleep(2.5)

        await client.send_message(stickers_bot, emoji)
        await asyncio.sleep(2)

        await client.send_message(stickers_bot, "/done")
        await asyncio.sleep(1)

        print(f"SUCCESS: Sticker added to pack https://t.me/addstickers/{PACK_SHORT_NAME}")
    finally:
        await client.disconnect()
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        if os.path.exists(sticker_file):
            try:
                os.remove(sticker_file)
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
