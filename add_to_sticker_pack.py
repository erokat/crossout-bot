import os
import sys
import asyncio
import random
import argparse
from PIL import Image
from telethon import TelegramClient

from config import load_config, SESSION_PATH, MEDIA_DIR, LOCK_PATH
from db import session_flock

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

async def add_sticker_to_pack(client, sticker_file, emoji):
    stickers_bot = await client.get_entity("Stickers")
    async with client.conversation(stickers_bot, timeout=15) as conv:
        # 1. Reset any stale state
        await conv.send_message("/cancel")
        await conv.get_response()

        # 2. Request adding sticker
        await conv.send_message("/addsticker")
        await conv.get_response()

        # 3. Specify target sticker pack
        await conv.send_message(PACK_SHORT_NAME)
        await conv.get_response()

        # 4. Upload sticker file as document
        await conv.send_file(sticker_file, force_document=True)
        await conv.get_response()

        # 5. Send matching emoji
        await conv.send_message(emoji)
        await conv.get_response()

        # 6. Finalize with /done
        await conv.send_message("/done")
        final_resp = await conv.get_response()

        print(f"SUCCESS: Sticker added to pack https://t.me/addstickers/{PACK_SHORT_NAME}")
        return True

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

    cfg = load_config()

    try:
        # Use session_flock with 15s timeout instead of infinite blocking fcntl.flock
        with session_flock(LOCK_PATH, timeout=15.0):
            client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
            await client.connect()

            if not await client.is_user_authorized():
                await client.disconnect()
                sys.stderr.write("Error: Telethon session not authorized\n")
                sys.exit(1)

            try:
                await add_sticker_to_pack(client, sticker_file, emoji)
            finally:
                await client.disconnect()
    except TimeoutError:
        sys.stderr.write("Error: Timeout acquiring session lock for sticker pack operation\n")
        sys.exit(1)
    except asyncio.TimeoutError:
        sys.stderr.write("Error: Timeout waiting for response from @Stickers bot\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error during sticker addition: {e}\n")
        sys.exit(1)
    finally:
        if os.path.exists(sticker_file):
            try:
                os.remove(sticker_file)
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
