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
    render_demotivator,
    clean_canvas_text
)

def is_photo_editor_request(text, has_photo=False):
    if not text:
        return has_photo
    t = text.lower().strip()

    # СТРОЖАЙШЕ: Запросы на стикерпак НЕ являются запросами на фоторедактор!
    if any(w in t for w in ["стикерпак", "стикер пак", "в стикерпак", "в пак", "в стикеры", "в стикер", "стикеры", "стикер"]):
        # Исключение: только если явно просят наложить стикер поверх фото
        if not any(w in t for w in ["на фото", "на картинку", "на изображение"]):
            return False

    # Запросы на сохранение или добавление картинки (без явного запроса на текст/фильтр)
    if any(w in t for w in ["добавь эту картинку", "добавь это фото", "добавь эту фотку", "добавь именно эту", "закинь эту", "сохрани эту"]):
        if not any(w in t for w in ["надпись", "подпись", "текст", "на фото"]):
            return False

    # СТРОЖАЙШЕ: Если фото НЕТ, и пользователь просит СГЕНЕРИРОВАТЬ, НАРИСОВАТЬ или СОЗДАТЬ картинку/мем:
    # это запрос на ГЕНЕРАЦИЮ (Meme Generator / AI), а НЕ редактирование существующего фото!
    if not has_photo:
        generation_verbs = [
            "сгенерируй", "создай", "нарисуй", "придумай", "склепай", "запили", "сделай мем",
            "найди", "скинь", "поищи", "покажи", "скачай", "в интернете", "из интернета"
        ]
        if any(w in t for w in generation_verbs):
            return False
        if any(w in t for w in ["картинку", "картинка", "пикчу", "мем", "мемчик", "мемасик"]):
            return False

    explicit_triggers = [
        "добавь надпись", "сделай надпись", "напиши на фото", "напиши на картинке",
        "на картинке напиши", "на фото напиши", "добавь текст", "прикрепи текст",
        "подпиши фото", "подпиши картинку", "подпиши", "сделай мем из фото",
        "сделай мем с этим фото", "сделай мем из этой картинки", "сделай мем из этой фотки",
        "наложи текст", "сделай демотиватор", "вставь текст", "допиши",
        "замени надпись", "замени на этой картинке", "поменяй надпись", "поменяй текст", "переделай текст", "переделай надпись", "замени текст",
        "добавь на фото", "прилепи на фото", "вставь на фото", "наложи на фото",
        "прилепи", "наложи картинку", "добавь картинку на фото", "вставь картинку на фото",
        "на лицо", "добавь на лицо", "прилепи на лицо", "вставь на лицо", "прифотошопь",
        "черно-бел", "черно бел", "ч/б", "чб", "сепия", "негатив", "инвертируй",
        "размой", "размыть", "заблюрь", "блюр", "резкость", "зашакаль", "пережарь",
        "deepfry", "дипфрай", "поверни", "переверни", "обрежь", "квадрат",
        "спич баббл", "спичбаббл", "облачко с текстом", "облако текста", "пусть скажет"
    ]
    if any(tr in t for tr in explicit_triggers):
        return True

    # If photo is already attached/replied and user asks to edit something
    if has_photo:
        if any(w in t for w in ["надпись", "подпись", "текст", "напиши", "титры", "замени", "поменяй", "переделай"]):
            return True
        if any(w in t for w in [
            "фильтр", "эффект", "наложи на фото", "вставь на фото", "поверни", "обрежь", "заблюрь", "чб",
            "на лицо", "лицо", "добавь", "прилепи", "наложи", "прифотошопь", "вставь", "замени", "слизнекот", "слизнец"
        ]):
            return True

    return False

def parse_caption_parts(raw_caption):
    """
    Разделяет текст на верхнюю и нижнюю части (если есть разделитель или ключевые слова)
    и надежно отсекает любые префиксы команд ('замени на этой картинке надпись на...').
    """
    t = raw_caption.strip()
    if not t:
        return "", ""

    # Проверяем, было ли в запросе явное указание на расположение текста сверху/снизу
    has_explicit_top = bool(re.search(r"(?i)\b(?:сверху|в\s*верху|наверху|сверху\s+картинки|наверху\s+фото)\b", t))
    has_explicit_bot = bool(re.search(r"(?i)\b(?:снизу|в\s*низу|под\s+фото|под\s+картинкой)\b", t))

    # 0. Отсекаем обращение к боту и вежливые слова
    t = re.sub(r"(?i)^(?:!бот|!bot|/бот|/bot|бот[,\s]*|ботик[,\s]*|пожалуйста[,\s]*|плиз[,\s]*)\s*", "", t).strip()

    # 1. Отсекаем глаголы и формулировки замены/редактирования/добавления надписи:
    # 'замени на этой картинке надпись на ...' -> '...'
    # 'поменяй текст на фото на ...' -> '...'
    # 'добавь надпись на картинку ...' -> '...'
    pat = (
        r"(?i)^(?:замени|поменяй|измени|переделай|добавь|напиши|сделай|наложи|прикрепи|вставь|запили|впиши|подпиши)"
        r"(?:\s+(?:на|в)?\s*(?:этом|этой|эту)?\s*(?:фото(?:графию)?|картинк[еу]|пикч[еу]))?"
        r"(?:\s+(?:надпись|подпись|текст|слова|титры|мем))?"
        r"(?:\s+(?:на|в)?\s*(?:этом|этой|эту)?\s*(?:фото(?:графию)?|картинк[еу]|пикч[еу]))?"
        r"(?:\s+(?:на|вместо\s+[^\n]+?\s+на))?"
        r"\s*[:,\s-]*\s*"
    )
    t = re.sub(pat, "", t).strip()

    # 2. Проверяем явное разделение на низ: '... и внизу картинки ...', '... снизу: ...', '... а снизу ...'
    split_pat = r"(?i)\s*(?:,\s*)?(?:\b(?:и|а)\s+)?(?:в\s*низу|снизу|под\s+картинкой|под\s+фото)(?:\s+картинки|\s+фото|\s+напиши|\s+текст|\s+надпись)*\s*[:\s-]+\s*"
    parts = re.split(split_pat, t, maxsplit=1)
    if len(parts) == 2:
        top = re.sub(r"(?i)^(?:в\s*верху|сверху|наверху|сверху\s+картинки)[:\s-]*", "", parts[0]).strip()
        bot = parts[1].strip()
        return top, bot

    # 3. 'сверху: ... снизу: ...'
    m_top_bot = re.search(r"(?i)(?:в\s*верху|сверху|наверху)\s*[:\s-]+\s*(.+?)\s+(?:в\s*низу|снизу)\s*[:\s-]+\s*(.+)", t)
    if m_top_bot:
        return m_top_bot.group(1).strip(), m_top_bot.group(2).strip()

    # 4. Явное указание только снизу: 'снизу: ...'
    m_bot_only = re.search(r"(?i)^(?:в\s*низу|снизу|под\s+фото|под\s+картинкой)\s*[:\s-]+\s*(.+)$", t)
    if m_bot_only:
        return "", m_bot_only.group(1).strip()

    # 5. Явное указание только сверху: 'сверху: ...'
    m_top_only = re.search(r"(?i)^(?:в\s*верху|сверху|наверху)\s*[:\s-]+\s*(.+)$", t)
    if m_top_only:
        return m_top_only.group(1).strip(), ""

    # 6. Разделители '//' или перевод строки
    if "//" in t:
        p = [x.strip() for x in t.split("//", 1)]
        return p[0], p[1]
    if "\n" in t:
        p = [x.strip() for x in t.split("\n", 1)]
        return p[0], p[1]

    # 7. Контрасты и противопоставления: 'верити, не верити, но тут три верити'
    m_contrast = re.search(r"(?i)^(.+?[,;])\s*(но тут|а тут|но в итоге|но на самом деле)\s*(.+)$", t)
    if m_contrast:
        top = m_contrast.group(1).strip()
        bot = f"{m_contrast.group(2).capitalize()} {m_contrast.group(3).strip()}"
        return top, bot

    # 8. Одиночный текст: если пользователь явно просил сверху — ставим наверх, иначе внизу
    clean_single = re.sub(r"(?i)^(?:в\s*верху|сверху|наверху|в\s*низу|снизу)[:\s-]*", "", t).strip()
    if has_explicit_top and not has_explicit_bot:
        return clean_single, ""
    else:
        return "", clean_single

def extract_caption_text(text):
    """
    Извлекает чистый текст для надписи из команды пользователя,
    полностью удаляя мета-команды ('замени на картинке надпись на...').
    """
    if not text:
        return ""
    t = text.strip()

    # Запросы на стикерпак не являются надписью
    if any(w in t.lower() for w in ["стикерпак", "стикер пак", "в стикерпак", "в пак", "в стикеры", "в стикер"]):
        return ""

    top, bot = parse_caption_parts(t)
    if top and bot:
        return f"{top}\n{bot}"
    elif bot:
        return bot
    elif top:
        return top

    return t

def render_photo_overlay(base_img, top_text="", bottom_text="", single_text=""):
    """
    Накладывает читаемый текст прямо на фото (Instagram/Telegram Stories/VK style).
    - Масштабирует изображение под комфортный размер для Telegram mobile (макс 1000-1200) без искажения пропорций.
    - Текст накладывается прямо на фото с четкой контрастной обводкой (stroke), без черного фона и плашек.
    - Безопасная видимость без обрезки и перекрытий.
    """
    # Преобразуем RGBA с прозрачностью на белый фон, исключая превращение прозрачности в черные пиксели
    if base_img.mode in ("RGBA", "LA") or (base_img.mode == "P" and "transparency" in base_img.info):
        rgba = base_img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        base_img = Image.alpha_composite(bg, rgba).convert("RGB")
    elif base_img.mode != "RGB":
        base_img = base_img.convert("RGB")

    W, H = base_img.size
    target_w = 1000
    scale = min(target_w / W, 1200 / H)
    if min(W * scale, H * scale) < 300:
        upscale = 300 / min(W * scale, H * scale)
        if max(W * scale, H * scale) * upscale <= 1600:
            scale *= upscale
    new_w = max(1, int(round(W * scale)))
    new_h = max(1, int(round(H * scale)))
    canvas = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas_w, canvas_h = canvas.size
    draw = ImageDraw.Draw(canvas)

    top = clean_canvas_text(top_text.strip())
    bot = clean_canvas_text(bottom_text.strip())
    single = clean_canvas_text(single_text.strip())

    if not top and not bot and single:
        t_cand, b_cand = parse_caption_parts(single)
        if b_cand:
            top, bot = clean_canvas_text(t_cand), clean_canvas_text(b_cand)
        elif t_cand and single.lower().startswith("сверху"):
            top = clean_canvas_text(t_cand)
        else:
            bot = single

    font_size = max(24, int(canvas_w * 0.048))
    # Адаптация размера шрифта при длинном тексте или низком разрешении
    total_words = len(top.split()) + len(bot.split())
    if total_words > 12 or (canvas_h < 500 and total_words > 6):
        font_size = max(20, int(font_size * 0.8))

    font = get_font("russo", font_size)
    stroke_w = max(4, int(round(font_size * 0.10)))
    line_h = int(font_size * 1.35)

    y_top_end = 0
    if top:
        lines = wrap_text(draw, top, font, canvas_w - 80)
        y_start = max(20, int(canvas_h * 0.08))
        for i, l in enumerate(lines):
            clean_l = clean_canvas_text(l)
            bb = draw.textbbox((0, 0), clean_l, font=font, stroke_width=stroke_w)
            lw = bb[2] - bb[0]
            lx = (canvas_w - lw) // 2 - bb[0]
            ly = y_start + i * line_h
            draw_outlined_text(draw, (lx, ly), clean_l, font=font, fill="#FFFFFF", stroke_fill="#000000", stroke_width=stroke_w)
        y_top_end = y_start + len(lines) * line_h

    if bot:
        lines = wrap_text(draw, bot, font, canvas_w - 80)
        total_text_h = len(lines) * line_h
        bottom_pad = max(20, int(canvas_h * 0.08))
        y_start = canvas_h - total_text_h - bottom_pad
        min_y = (y_top_end + 15) if top else 20
        y_start = max(min_y, y_start)
        for i, l in enumerate(lines):
            clean_l = clean_canvas_text(l)
            bb = draw.textbbox((0, 0), clean_l, font=font, stroke_width=stroke_w)
            lw = bb[2] - bb[0]
            lx = (canvas_w - lw) // 2 - bb[0]
            ly = y_start + i * line_h
            draw_outlined_text(draw, (lx, ly), clean_l, font=font, fill="#FFFFFF", stroke_fill="#000000", stroke_width=stroke_w)

    return canvas

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

    top_text, bottom_text = parse_caption_parts(user_instruction)
    if top_text and bottom_text:
        caption_text = f"{top_text}\n{bottom_text}"
    else:
        caption_text = top_text or bottom_text or extract_caption_text(user_instruction) or user_instruction.strip()

    # Определяем стиль
    instr_lower = user_instruction.lower()
    if style == "auto":
        if "демотиватор" in instr_lower:
            style = "demotivator"
        elif "импакт" in instr_lower or "impact" in instr_lower or "шрифт сверху и снизу" in instr_lower:
            style = "impact"
        elif "шапка" in instr_lower or "белая карточка" in instr_lower:
            style = "top_card"
        else:
            # По умолчанию: современный оверлей на фото с крупным читаемым текстом без фона
            style = "overlay"

    raw_img = Image.open(photo_path)
    if raw_img.mode in ("RGBA", "LA") or (raw_img.mode == "P" and "transparency" in raw_img.info):
        rgba = raw_img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, rgba).convert("RGB")
    else:
        img = raw_img.convert("RGB")

    if style == "demotivator":
        title = top_text or caption_text
        sub = bottom_text or ""
        canvas = render_demotivator(img, title, sub)
    elif style == "impact":
        top = top_text or caption_text
        bot = bottom_text or ""
        canvas = render_impact_meme(img, top, bot)
    elif style == "top_card":
        if bottom_text:
            canvas = render_caption_meme(img, text_top=top_text.capitalize(), text_bottom=bottom_text.upper())
        else:
            canvas = render_caption_meme(img, text_top=caption_text.capitalize())
    else:
        # Default: Стильный оверлей прямо на фото, гарантированно видимый в Telegram
        canvas = render_photo_overlay(img, top_text=top_text, bottom_text=bottom_text, single_text=caption_text)

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

STICKER_LOCAL_ASSETS = {
    "газген": "gasgen.png",
    "gasgen": "gasgen.png",
    "генератор": "gasgen.png",
    "птур": "ptur.png",
    "ptur": "ptur.png",
    "ракета": "ptur.png",
    "капкан": "kapkan.png",
    "kapkan": "kapkan.png",
    "ловушка": "kapkan.png",
    "вереск": "heather.png",
    "heather": "heather.png",
    "ховер": "hover.png",
    "hover": "hover.png",
    "мамонт": "mammoth.png",
    "mammoth": "mammoth.png",
    "пушка": "mammoth.png",
    "скорпион": "scorpion.png",
    "скорп": "scorpion.png",
    "йети": "yeti.png",
    "yeti": "yeti.png",
    "невидимка": "yeti.png",
    "инвиз": "yeti.png",
    "жнец": "harvester.png",
    "комбайн": "harvester.png",
    "колесо": "wheel1.png",
    "клоун": "tpl_clown.png",
    "доге": "tpl_doge.png",
    "doge": "tpl_doge.png",
    "копье": "spear.png",
    "копьё": "spear.png",
    "огонь": "fire_0.png",
    "пламя": "fire_1.png",
    "слизнекот": "slugcat_head_clean.png",
    "слизнец": "slugcat_head_clean.png",
    "slugcat": "slugcat_head_clean.png"
}

def find_or_download_sticker(sticker_query):
    """Находит стикер в локальных ассетах или ищет прозрачный PNG в сети."""
    q_low = sticker_query.lower().strip()

    # 1. Проверяем локальные ассеты Crossout и мемов
    for kw, asset_fn in STICKER_LOCAL_ASSETS.items():
        if kw in q_low:
            local_p = os.path.join(MEDIA_DIR, asset_fn)
            if os.path.exists(local_p):
                return local_p

    # 2. Ищем прозрачный PNG стикер в интернете через Bing
    stickers_dir = os.path.join(MEDIA_DIR, "stickers")
    os.makedirs(stickers_dir, exist_ok=True)
    clean_q = re.sub(r"(?i)^(?:добавь|прилепи|наложи|вставь|на фото|на картинку|картинку|стикер|фото)\s*", "", q_low).strip()
    if not clean_q:
        clean_q = "thug life glasses"

    import hashlib
    import urllib.request
    import urllib.parse
    h = hashlib.md5(clean_q.encode()).hexdigest()[:10]
    cached_sticker = os.path.join(stickers_dir, f"stk_{h}.png")
    if os.path.exists(cached_sticker) and os.path.getsize(cached_sticker) > 1000:
        return cached_sticker

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    search_term = f"{clean_q} transparent png sticker clipart"
    try:
        b_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(search_term)}"
        req = urllib.request.Request(b_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            found = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', html)

        for u in found[:8]:
            try:
                req2 = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req2, timeout=6) as resp2:
                    data = resp2.read()
                    if len(data) < 2000:
                        continue
                    temp_p = cached_sticker + ".tmp"
                    with open(temp_p, "wb") as f:
                        f.write(data)
                    with Image.open(temp_p) as im:
                        rgba = im.convert("RGBA")
                        rgba.save(cached_sticker, "PNG")
                    if os.path.exists(temp_p):
                        os.remove(temp_p)
                    return cached_sticker
            except Exception:
                continue
    except Exception as e:
        print(f"[STICKER SEARCH ERROR] {e}")

    # Fallback to local gasgen if nothing found
    fallback = os.path.join(MEDIA_DIR, "gasgen.png")
    return fallback if os.path.exists(fallback) else None

def overlay_sticker_on_image(base_img, sticker_query, pos_name="auto", scale=0.35):
    """Накладывает стикер / объект на изображение с альфа-прозрачностью."""
    sticker_path = find_or_download_sticker(sticker_query)
    if not sticker_path or not os.path.exists(sticker_path):
        return base_img

    try:
        stk_raw = Image.open(sticker_path).convert("RGBA")
        W, H = base_img.size

        # Масштабируем стикер
        target_w = max(40, int(W * scale))
        stk_scale = target_w / stk_raw.width
        target_h = max(40, int(stk_raw.height * stk_scale))
        stk_resized = stk_raw.resize((target_w, target_h), Image.Resampling.LANCZOS)
        sw, sh = stk_resized.size

        # Определяем позицию
        p_low = (pos_name or "").lower()
        if "лицо" in p_low or "face" in p_low or "морду" in p_low:
            x = int(W * 0.42)
            y = int(H * 0.32)
        elif "голову" in p_low or "сверху" in p_low or "head" in p_low or "top" in p_low:
            x = (W - sw) // 2
            y = max(10, int(H * 0.08))
        elif "снизу справа" in p_low or "bottom-right" in p_low:
            x = max(10, W - sw - 20)
            y = max(10, H - sh - 20)
        elif "снизу слева" in p_low or "bottom-left" in p_low:
            x = 20
            y = max(10, H - sh - 20)
        elif "сверху справа" in p_low or "top-right" in p_low:
            x = max(10, W - sw - 20)
            y = 20
        elif "сверху слева" in p_low or "top-left" in p_low:
            x = 20
            y = 20
        elif "снизу" in p_low or "bottom" in p_low:
            x = (W - sw) // 2
            y = max(10, H - sh - 30)
        else:
            # Центр по умолчанию
            x = (W - sw) // 2
            y = (H - sh) // 2

        # Преобразуем base_img в RGBA для наложения
        base_rgba = base_img.convert("RGBA")
        overlay_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        overlay_canvas.paste(stk_resized, (x, y), stk_resized)
        res_rgba = Image.alpha_composite(base_rgba, overlay_canvas)
        return res_rgba.convert("RGB")
    except Exception as e:
        print(f"[STICKER OVERLAY ERROR] {e}")
        return base_img

def apply_visual_filter(img, filter_type):
    """Применяет визуальный фильтр к изображению."""
    from PIL import ImageEnhance, ImageFilter, ImageOps
    f_low = filter_type.lower()

    if any(w in f_low for w in ["чб", "ч/б", "черно-бел", "черно бел", "серый", "gray"]):
        return img.convert("L").convert("RGB")

    if any(w in f_low for w in ["сепия", "sepia", "винтаж"]):
        gray = img.convert("L")
        sepia = Image.merge("RGB", [
            gray.point(lambda p: min(255, int(p * 1.15))),
            gray.point(lambda p: min(255, int(p * 0.95))),
            gray.point(lambda p: min(255, int(p * 0.75)))
        ])
        return sepia

    if any(w in f_low for w in ["негатив", "инверт"]):
        return ImageOps.invert(img.convert("RGB"))

    if any(w in f_low for w in ["размой", "блюр", "blur"]):
        return img.filter(ImageFilter.GaussianBlur(radius=6))

    if any(w in f_low for w in ["резкость", "sharpen"]):
        return img.filter(ImageFilter.SHARPEN)

    if any(w in f_low for w in ["зашакаль", "пережарь", "deepfry", "дипфрай", "шакал"]):
        # Экстремальная сатурация, контраст и резкость (стиль жареного мема)
        enh = ImageEnhance.Color(img).enhance(2.8)
        enh = ImageEnhance.Contrast(enh).enhance(2.2)
        enh = ImageEnhance.Sharpness(enh).enhance(3.5)
        return enh

    if any(w in f_low for w in ["ярче", "яркость"]):
        return ImageEnhance.Brightness(img).enhance(1.4)

    if any(w in f_low for w in ["темнее"]):
        return ImageEnhance.Brightness(img).enhance(0.7)

    if any(w in f_low for w in ["контраст"]):
        return ImageEnhance.Contrast(img).enhance(1.6)

    if "поверни на 90" in f_low or "поворот 90" in f_low:
        return img.rotate(270, expand=True)

    if "поверни на 180" in f_low or "переверни" in f_low:
        return img.rotate(180, expand=True)

    if "поверни на 270" in f_low:
        return img.rotate(90, expand=True)

    if any(w in f_low for w in ["квадрат", "квадратным", "1:1"]):
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        return img.crop((left, top, left + min_dim, top + min_dim))

    return img

def add_speech_bubble(img, text, tip_dir="bottom"):
    """Создает мемное облачко реплики (speech bubble) с текстом."""
    from PIL import ImageDraw
    W, H = img.size
    canvas = img.copy().convert("RGB")
    draw = ImageDraw.Draw(canvas)

    bubble_w = max(200, int(W * 0.75))
    font_size = max(18, int(bubble_w * 0.055))
    font = get_font("russo", font_size)

    lines = wrap_text(draw, text.strip(), font, bubble_w - 40)
    line_h = int(font_size * 1.35)
    bubble_h = len(lines) * line_h + 30

    bx0 = (W - bubble_w) // 2
    by0 = 20
    bx1 = bx0 + bubble_w
    by1 = by0 + bubble_h

    # Рисуем белое облачко с черным контуром
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=15, fill="#FFFFFF", outline="#000000", width=3)
    # Хвостик баббла вниз
    tip_x = W // 2
    draw.polygon([(tip_x - 15, by1), (tip_x + 15, by1), (tip_x - 5, by1 + 25)], fill="#FFFFFF", outline="#000000")
    # Перекрываем шов белой линией
    draw.line([(tip_x - 13, by1), (tip_x + 13, by1)], fill="#FFFFFF", width=3)

    # Текст внутри баббла
    for i, l in enumerate(lines):
        clean_l = clean_canvas_text(l)
        bb = draw.textbbox((0, 0), clean_l, font=font)
        lw = bb[2] - bb[0]
        lx = bx0 + (bubble_w - lw) // 2
        ly = by0 + 15 + i * line_h
        draw.text((lx, ly), clean_l, font=font, fill="#000000")

    return canvas

def process_universal_photo_command(photo_path, command_text):
    """
    Универсальный диспетчер обработки фото:
    - Добавление стикеров / предметов / ассетов
    - Визуальные фильтры (чб, сепия, размытие, жарка/deepfry, поворот, обрезка)
    - Спич-бабблы (облачка реплик)
    - Демотиваторы и текстовые оверлеи
    Возвращает (output_path, reply_caption).
    """
    if not photo_path or not os.path.exists(photo_path):
        raise FileNotFoundError(f"Photo not found: {photo_path}")

    raw_img = Image.open(photo_path)
    if raw_img.mode in ("RGBA", "LA") or (raw_img.mode == "P" and "transparency" in raw_img.info):
        rgba = raw_img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, rgba).convert("RGB")
    else:
        img = raw_img.convert("RGB")

    t_low = command_text.lower()
    reply_cap = "Лови готовое фото! 📸🔥"

    # 1. Спич-баббл / облако с текстом
    if any(w in t_low for w in ["спич баббл", "спичбаббл", "облачко", "облако", "пусть скажет"]):
        m_txt = re.search(r"(?i)(?:спич\s*баббл|облачко\s+с\s+текстом|пусть\s+скажет|облако|текст)[:\s-]+\s*(.+)$", command_text)
        bubble_text = m_txt.group(1).strip() if m_txt else command_text.strip()
        img = add_speech_bubble(img, bubble_text)
        reply_cap = "Прилепил облачко с текстом, как в комиксе! 💬✨"

    # 2. Демотиватор
    elif "демотиватор" in t_low:
        out_p, _ = edit_photo_with_caption(photo_path, command_text, style="demotivator")
        return out_p, "Держи классический демотиватор! 🖤🖼️"

    # 3. Текстовая надпись на фото (ПРИОРИТЕТ над стикерами!)
    elif any(w in t_low for w in ["надпись", "подпись", "текст", "титры", "напиши", "подпиши", "допиши", "замени", "поменяй", "переделай", "впиши"]):
        out_p, _ = edit_photo_with_caption(photo_path, command_text)
        return out_p, "Лови готовое фото с надписью! 📸🔥"

    # 4. Визуальные фильтры
    elif any(w in t_low for w in ["чб", "ч/б", "черно-бел", "сепия", "негатив", "инверт", "размой", "блюр", "резкость", "зашакаль", "пережарь", "deepfry", "ярче", "темнее", "поверни", "квадрат"]):
        img = apply_visual_filter(img, command_text)
        if any(w in t_low for w in ["зашакаль", "пережарь", "deepfry"]):
            reply_cap = "Зашакалил фото по высшему разряду, хрустит как свежий Газген! 💀🔥"
        elif any(w in t_low for w in ["чб", "черно-бел"]):
            reply_cap = "Сделал стильное черно-белое фото! 🎞️🖤"
        elif any(w in t_low for w in ["размой", "блюр"]):
            reply_cap = "Наложил мягкое размытие (blur)! 🌫️📸"
        else:
            reply_cap = "Применил визуальный эффект к фото! ✨🎨"

    # 5. Добавление стикера / предмета / ассета на фото
    elif any(w in t_low for w in ["добавь на фото", "прилепи на фото", "вставь на фото", "наложи на фото", "прилепи", "наложи картинку", "добавь картинку", "вставь картинку", "на лицо", "прифотошопь", "стикер"]) or any(kw in t_low for kw in STICKER_LOCAL_ASSETS):
        # Извлекаем название предмета/стикера
        m_stk = re.search(r"(?i)(?:добавь|прилепи|наложи|вставь|прифотошопь)(?:\s+(?:на\s+фото|на\s+картинку|на\s+лицо(?:\s+[а-я]+)?))?\s+(.+?)(?:\s+(?:сверху|снизу|на голову|на лицо|по центру|слева|справа)|$)", command_text)
        sticker_q = m_stk.group(1).strip() if m_stk else ""
        if not sticker_q or any(w in sticker_q.lower() for w in ["этот", "эту", "фото", "картинку"]):
            for kw in STICKER_LOCAL_ASSETS:
                if kw in t_low:
                    sticker_q = kw
                    break
        if not sticker_q:
            sticker_q = "газген"

        pos = "auto"
        if "лицо" in t_low or "морду" in t_low or "face" in t_low:
            pos = "face"
        elif "голову" in t_low or "сверху" in t_low:
            pos = "head"
        elif "снизу" in t_low:
            pos = "bottom"
        elif "справа" in t_low:
            pos = "top-right"
        elif "слева" in t_low:
            pos = "top-left"

        img = overlay_sticker_on_image(img, sticker_q, pos_name=pos)
        reply_cap = f"Прилепил {sticker_q} прямо на фото! 🚜🔥"

    # 6. Fallback к текстовой надписи
    else:
        out_p, _ = edit_photo_with_caption(photo_path, command_text)
        return out_p, "Держи готовое фото с надписью! 📸🔥"

    # Сохраняем результат
    ts = int(time.time())
    out_filename = f"edited_photo_{ts}.jpg"
    out_path = os.path.join(MEDIA_DIR, out_filename)
    img.save(out_path, format="JPEG", quality=95)

    saved_copy = os.path.join(SAVED_MEMES_DIR, out_filename)
    shutil.copy2(out_path, saved_copy)

    if os.path.exists(ANDROID_PHOTOS_DIR):
        try:
            shutil.copy2(out_path, os.path.join(ANDROID_PHOTOS_DIR, out_filename))
        except Exception:
            pass

    return out_path, reply_cap

