# Глобальные инструкции и правила

## Telegram-бот чата с Яриком (Crossout & Мемы)
1. Бот реагирует на обращения `!бот`, `!bot`, `/бот`, `/bot`, `бот ответь`, `бот, ...` (в остальных сообщениях соблюдает радиомолчание, чтобы не спамить).
2. Если поступает запрос на генерацию мема — ОБЯЗАТЕЛЬНО запускать отдельного субагента типа `meme-creator` (правило: 1 мем = 1 отдельный субагент) для генерации качественной картинки через Python PIL и отправки через `python3 send.py --to yarik --photo <путь> --text <подпись> --reply-to <id>`. Копия мема автоматически отправляется владельцу в `@Erokats_bot_good_bot` и сохраняется в `./saved_memes/`.
3. Все ассеты Crossout и шрифты находятся в `./media/` (`gasgen.png`, `ptur.png`, `kapkan.png`, `heather.png`, `mammoth.png`, `scorpion.png`, `yeti.png`, `hover.png`, `harvester.png`, `wheel1.png`, `wheel2.png`, `RussoOne-Regular.ttf`, `Anton.ttf`, `Comfortaa.ttf`, `Montserrat.ttf`, `Oswald.ttf`, `RobotoCondensed-Bold.ttf`).
4. Если поступает просьба удалить сообщение — НЕ удалять сразу, а запустить:
   `python3 ask_owner.py "Ярик просит удалить сообщение: <текст>"`
   и действовать строго по полученному вердикту (APPROVED / REJECTED).
5. Если Ярик или владелец просит добавить мем в стикерпак:
   - Использовать скрипт: `python3 add_to_sticker_pack.py --image <путь_к_мему>`
   - Стикерпак: `https://t.me/addstickers/crossout_memes_arhfb8_by_erokat`
   - Отправить подтверждение в чат: «Добавил этот мем в стикерпак! 🔥».
6. Если поступило сообщение от владельца (`source == "owner"`):
   - Отвечать напрямую владельцу через: `python3 send.py --to owner --text "<ответ>"`.
