import os
import sys
import asyncio
import logging
import re
from fastapi import FastAPI
import uvicorn
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from meme_generator import generate_crossout_meme

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("crossout_bot")

API_ID = int(os.environ.get("API_ID", "36987621"))
API_HASH = os.environ.get("API_HASH", "85e94b29eb77b949989047b418caad32")
SESSION_STRING = os.environ.get("TELEGRAM_STRING_SESSION", "")
YARIK_CHAT_ID = int(os.environ.get("YARIK_CHAT_ID", "6271387044"))

app = FastAPI(title="Crossout Telegram Bot")

@app.get("/")
def read_root():
    return {"status": "ok", "service": "crossout-telegram-bot", "chat_target": YARIK_CHAT_ID}

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

bot_sent_ids = set()

async def telegram_worker():
    if not SESSION_STRING:
        logger.error("TELEGRAM_STRING_SESSION is not set in environment variables!")
        return

    logger.info("Initializing Telegram client with StringSession...")
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        logger.error("Telegram session string is not authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    logger.info(f"Connected to Telegram as {me.first_name} (@{me.username})")

    @client.on(events.NewMessage(chats=YARIK_CHAT_ID))
    async def handler(event):
        msg = event.message
        if msg.id in bot_sent_ids:
            return

        text = msg.message or ""
        is_from_yarik = (msg.sender_id == YARIK_CHAT_ID)
        is_mention = is_bot_mention(text)

        # Режим радиомолчания: реагируем только при вызове бота
        if not is_mention:
            return

        logger.info(f"Handling summon from {'Yarik' if is_from_yarik else 'Owner'}: {text!r}")
        t_low = text.lower()

        # 1. Запрос на удаление
        if "удали" in t_low:
            resp = await client.send_message(
                YARIK_CHAT_ID,
                "⚠️ Запрос на удаление получен! По правилам чата, удаление сообщений требует подтверждения владельца аккаунта 🛡️",
                reply_to=msg.id
            )
            bot_sent_ids.add(resp.id)
            return

        # 2. Запрос на мем
        if "мем" in t_low or "пикч" in t_low or "картинк" in t_low:
            meme_file = generate_crossout_meme(theme=text)
            caption = "Свежий авторский мем по Пустошам готов! 🚜💥"
            if "автосборк" in t_low:
                caption = "Когда доверился кнопке «Автосборка» в гараже 😂🤖"
            resp = await client.send_file(
                YARIK_CHAT_ID,
                meme_file,
                caption=caption,
                reply_to=msg.id
            )
            bot_sent_ids.add(resp.id)
            return

        # 3. Вопрос или объяснение
        if "обьясни" in t_low or "поясни" in t_low or "расскажи" in t_low:
            resp = await client.send_message(
                YARIK_CHAT_ID,
                "Поясняю по фактам: в Пустошах закон один — если у тебя открыт Газген, то даже птица, пролетающая мимо, может отправить тебя в ангар 😂💥 А если серьезно, задавай конкретный вопрос, разберем!",
                reply_to=msg.id
            )
            bot_sent_ids.add(resp.id)
            return

        # 4. Общий ответ на призыв
        resp = await client.send_message(
            YARIK_CHAT_ID,
            "На связи! 🤖 Слушаю внимательно. Могу сгенерить мем (`!бот сделай мем...`) или пояснить за мету и крафты в Crossout!",
            reply_to=msg.id
        )
        bot_sent_ids.add(resp.id)

    logger.info("Telegram event listener active...")
    await client.run_until_disconnected()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(telegram_worker())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
