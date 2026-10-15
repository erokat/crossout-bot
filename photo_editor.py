# -*- coding: utf-8 -*-
"""
PHOTO EDITOR & CAPTION ENGINE for Crossout Userbot
Полноценный фоторедактор для Telegram-бота:
- Добавление надписей и подписей к фото
- Создание мемов из пользовательских фотографий
- Стили: Top Card (чистый мем), Impact (классический), Demotivator, Subtitle
- Поддержка шрифтов Russo One, Montserrat, Impact
- Автоматическое сохранение в /storage/emulated/0/Pictures/PhotosEditor
"""
import os
import re
import sys
import time
import shutil
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")
ANDROID_PHOTOS_DIR = "/storage/emulated/0/Pictures/PhotosEditor"

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)
if os.path.exists("/storage/emulated/0/Pictures"):
    os.makedirs(ANDROID_PHOTOS_DIR, exist_ok=True)

from meme_engine import (
    get_font,
    wrap_text,
    draw_outlined_text,
    render_caption_meme,
    render_impact_meme,
    render_demotivator
)

def is_photo_editor_request(text, has_photo=False):
    if not text:
        return has_photo
    t = text.lower().strip()

    explicit_triggers = [
        "добавь надпись", "сделай надпись", "напиши на фото", "напиши на картинке",
        "на картинке напиши", "на фото напиши", "добавь текст", "прикрепи текст",
        "подпиши фото", "подпиши картинку", "подпиши", "сделай мем из фото",
        "сделай мем с этим фото", "сделай мем из этой картинки", "сделай мем из этой фотки",
        "наложи текст", "сделай демотиватор", "вставь текст", "допиши"
    ]
    if any(tr in t for tr in explicit_triggers):
        return True

    # If photo is already attached/replied and user asks to add something
    if has_photo:
        if any(w in t for w in ["надпись", "подпись", "текст", "напиши", "титры"]):
            return True
        if any(w in t for w in ["сделай мем", "запили мем", "мемчик", "мем"]):
            return True

    return False

def extract_caption_text(text):
    if not text:
        return ""
    t = text.strip()

    patterns = [
        r"(?i)(?:^|\s)(?:бот|ботик)?\s*(?:пожалуйста|плиз)?\s*(?:добавь|сделай|напиши|прикрепи|наложи|запили)?\s*(?:надпись|подпись|текст|мем|титры|словечки)?\s*[:,\s-]+\s*(.+)$",
        r"(?i)(?:^|\s)(?:бот|ботик)?\s*(?:пожалуйста|плиз)?\s*(?:подпиши|напиши на фото|напиши на картинке|на фото напиши|сделай мем из этого фото|сделай мем с этим фото|сделай мем из этой картинки)\s*[:,\s-]*\s*(.+)$",
        r"(?i)(?:^|\s)(?:бот|ботик)?\s*добавь\s*[:,\s-]+\s*(.+)$"
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            cand = m.group(1).strip()
            cand = re.sub(r"^[:,\s-]+", "", cand).strip()
            # If cand isn't just common filler words
            if cand and cand.lower() not in ["надпись", "текст", "фото", "картинку", "пожалуйста"]:
                return cand

    # Fallback strip command prefix
    cleaned = re.sub(
        r"(?i)^(?:бот[,\s]*)?(?:пожалуйста[,\s]*)?(?:добавь[,\s]*)?(?:надпись|подпись|текст|напиши на фото|напиши на картинке|подпиши)[,\s:]*",
        "", t
    ).strip()
    return cleaned or t

def parse_caption_parts(raw_caption):
    """
    Разделяет текст на верхнюю и нижнюю части (если есть разделитель или ключевые слова)
    """
    text = raw_caption.strip()
    if not text:
        return "", ""

    # 1. Проверяем формат "сверху: ... снизу: ..."
    m_split = re.search(r"(?i)сверху[:\s]+(.+?)\s+снизу[:\s]+(.+)", text)
    if m_split:
        return m_split.group(1).strip(), m_split.group(2).strip()

    # 2. Проверяем явный разделитель через // или \n
    if "//" in text:
        parts = [p.strip() for p in text.split("//", 1)]
        return parts[0], parts[1]

    if "\n" in text:
        parts = [p.strip() for p in text.split("\n", 1)]
        return parts[0], parts[1]

    # 3. Проверяем разделители типа "но тут", "а тут", "когда ... но ..."
    m_split2 = re.search(r"(?i)^(.+?[,;])\s*(но тут|а тут|но в итоге|но на самом деле)\s*(.+)$", text)
    if m_split2:
        top_part = m_split2.group(1).strip()
        bot_part = f"{m_split2.group(2).capitalize()} {m_split2.group(3).strip()}"
        return top_part, bot_part

    return text, ""

def edit_photo_with_caption(photo_path, user_instruction, style="auto"):
    """
    Главная функция фоторедактора:
    - Открывает photo_path
    - Накладывает надпись по запросу user_instruction
    - Сохраняет результат
    - Возвращает путь к созданному файлу
    """
    if not photo_path or not os.path.exists(photo_path):
        raise FileNotFoundError(f"Input photo not found: {photo_path}")

    caption_text = extract_caption_text(user_instruction)
    if not caption_text:
        caption_text = user_instruction.strip()

    top_text, bottom_text = parse_caption_parts(caption_text)

    # Определяем стиль
    instr_lower = user_instruction.lower()
    if style == "auto":
        if "демотиватор" in instr_lower:
            style = "demotivator"
        elif "импакт" in instr_lower or "impact" in instr_lower or "шрифт сверху и снизу" in instr_lower:
            style = "impact"
        else:
            style = "top_card"

    img = Image.open(photo_path).convert("RGB")

    if style == "demotivator":
        title = top_text or caption_text
        sub = bottom_text or ""
        canvas = render_demotivator(img, title, sub)
    elif style == "impact":
        top = top_text or caption_text
        bot = bottom_text or ""
        canvas = render_impact_meme(img, top, bot)
    else:
        # Default: Top card modern clean meme
        # If we have both top and bottom, render top in header and bottom as punchline
        if bottom_text:
            canvas = render_caption_meme(img, text_top=top_text.capitalize(), text_bottom=bottom_text.upper())
        else:
            canvas = render_caption_meme(img, text_top=caption_text.capitalize())

    # Сохраняем результат
    ts = int(time.time())
    out_filename = f"edited_photo_{ts}.jpg"
    out_path = os.path.join(MEDIA_DIR, out_filename)
    canvas.save(out_path, format="JPEG", quality=95)

    # Сохраняем копию в saved_memes
    saved_copy = os.path.join(SAVED_MEMES_DIR, out_filename)
    shutil.copy2(out_path, saved_copy)

    # Сохраняем в Android PhotosEditor если директория существует
    if os.path.exists(ANDROID_PHOTOS_DIR):
        try:
            android_copy = os.path.join(ANDROID_PHOTOS_DIR, out_filename)
            shutil.copy2(out_path, android_copy)
        except Exception as e:
            print(f"[PHOTO EDITOR] Failed to copy to Android gallery: {e}")

    # Синхронизация на Google Drive
    try:
        from gdrive import upload_and_cleanup
        upload_and_cleanup(saved_copy, folder_type="memes")
    except Exception as e:
        print(f"[PHOTO EDITOR GDRIVE] {e}")

    return out_path, caption_text
