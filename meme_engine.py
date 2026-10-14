import os
import re
import sys
import time
import json
import random
import hashlib
import shutil
import urllib.request
import urllib.parse
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
TEMPLATES_DIR = os.path.join(MEDIA_DIR, "meme_templates")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")
ANDROID_PHOTOS_DIR = "/storage/emulated/0/Pictures/PhotosEditor"

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)
if os.path.exists("/storage/emulated/0/Pictures"):
    os.makedirs(ANDROID_PHOTOS_DIR, exist_ok=True)

# ----------------- FONT HELPERS -----------------

def get_font(name="russo", size=32):
    font_map = {
        "russo": [
            os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "bold": [
            os.path.join(MEDIA_DIR, "RobotoCondensed-Bold.ttf"),
            os.path.join(MEDIA_DIR, "Anton.ttf"),
            os.path.join(MEDIA_DIR, "Oswald.ttf"),
            os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
        ],
        "impact": [
            os.path.join(MEDIA_DIR, "Anton.ttf"),
            os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
            os.path.join(MEDIA_DIR, "RobotoCondensed-Bold.ttf"),
        ],
        "regular": [
            os.path.join(MEDIA_DIR, "RobotoCondensed-Bold.ttf"),
            os.path.join(MEDIA_DIR, "Comfortaa.ttf"),
            os.path.join(MEDIA_DIR, "Montserrat.ttf"),
        ]
    }
    candidates = font_map.get(name, font_map["russo"])
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    cur_line = []
    for w in words:
        test_line = " ".join(cur_line + [w])
        bb = draw.textbbox((0, 0), test_line, font=font)
        if bb[2] - bb[0] <= max_width:
            cur_line.append(w)
        else:
            if cur_line:
                lines.append(" ".join(cur_line))
                cur_line = [w]
            else:
                lines.append(w)
                cur_line = []
    if cur_line:
        lines.append(" ".join(cur_line))
    return lines

def draw_outlined_text(draw, pos, text, font, fill="white", stroke_fill="black", stroke_width=4):
    x, y = pos
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

# ----------------- CURATED POPULAR MEMES (2020-2022 & TIMELESS) -----------------

MEMES_2020_2022 = [
    {
        "name": "gigachad",
        "title": "GigaChad",
        "url": "https://i.imgflip.com/35bdwf.jpg",
        "keywords": ["гигачад", "gigachad", "сигма", "база", "базированный", "сигмач", "мужик"],
        "default_setup": "Да, я играю в Crossout на чистом Газгене и ховерах.",
        "default_punchline": "Как ты догадался?"
    },
    {
        "name": "trade_offer",
        "title": "Trade Offer",
        "url": "https://i.imgflip.com/54hjww.jpg",
        "keywords": ["сделка", "trade offer", "обмен", "предложение"],
        "default_setup": "ДЕЛО ПРЕДЛОЖЕНИЯ (TRADE OFFER):",
        "default_punchline": "Я получаю: твою жемчужину\nТы получаешь: 8 взрывных копий в лицо"
    },
    {
        "name": "think_mark",
        "title": "Think Mark Think",
        "url": "https://i.imgflip.com/58bk20.jpg",
        "keywords": ["подумай", "think mark", "неуязвимый", "омнимен"],
        "default_setup": "ПОДУМАЙ, ЯРИК, ПОДУМАЙ!",
        "default_punchline": "Зачем ставить Газген под кабину, если он детонирует от ветра?!"
    },
    {
        "name": "doge_vs_cheems",
        "title": "Buff Doge vs Cheems",
        "url": "https://i.imgflip.com/43a45p.png",
        "keywords": ["доге", "чимс", "раньше", "сейчас", "сравнение", "doge", "cheems"],
        "default_setup": "Игроки в 2020 vs Игроки в 2022",
        "default_punchline": "3 часа собирал броневик vs заплакал от дробовика"
    },
    {
        "name": "always_has_been",
        "title": "Always Has Been",
        "url": "https://i.imgflip.com/46e43q.png",
        "keywords": ["всегда был", "космонавты", "always has been", "предательство"],
        "default_setup": "Подожди, это всё был один сплошной рандом?",
        "default_punchline": "Всегда так и было."
    },
    {
        "name": "anakin_padme",
        "title": "Anakin Padme 4 Panel",
        "url": "https://i.imgflip.com/5c7lwq.png",
        "keywords": ["анакин", "падме", "ты же", "правда ведь"],
        "default_setup": "Я настроил билд и иду в рандом. — Мы же победим, правда?",
        "default_punchline": "Правда ведь?..."
    },
    {
        "name": "bernie_sanders",
        "title": "Bernie Mittens",
        "url": "https://i.imgflip.com/4v66v5.png",
        "keywords": ["берни", "варежки", "ожидание", "сижу"],
        "default_setup": "Я снова жду, пока починят баланс и подбор в боях...",
        "default_punchline": "Цикл 12-й, ничего не изменилось."
    },
    {
        "name": "mr_incredible_uncanny",
        "title": "Mr Incredible Becoming Uncanny",
        "url": "https://i.imgflip.com/6090bv.jpg",
        "keywords": ["мистер исключительный", "жуткий", "стадии боли", "mr incredible"],
        "default_setup": "Стадии осознания, когда в убежище Rain World закончился кислород",
        "default_punchline": "И до убежища осталось 3 экрана..."
    },
    {
        "name": "mahoraga",
        "title": "Mahoraga Adapting",
        "url": "https://i.imgflip.com/8fs267.jpg",
        "keywords": ["махорага", "бог", "адаптируется", "адаптация", "колесо", "дхарма", "jujutsu"],
        "default_setup": "Когда жизнь пытается добить тебя очередным ударом,",
        "default_punchline": "Но колесо Махораги уже сделало полный оборот. ☸️"
    },
    {
        "name": "drake",
        "title": "Drake Hotline Bling",
        "url": "https://i.imgflip.com/30b1gx.jpg",
        "keywords": ["дрейк", "drake", "нет да", "выбор"],
        "default_setup": "Сделать сбалансированный крафт с броней — НЕТ\nПоставить 4 Газгена и улететь в стратосферу — ДА",
        "default_punchline": "Гений инженерной мысли."
    },
    {
        "name": "two_buttons",
        "title": "Two Buttons",
        "url": "https://i.imgflip.com/1g8my4.jpg",
        "keywords": ["две кнопки", "сложный выбор", "кнопка", "пот"],
        "default_setup": "Сложный выбор в 3 часа ночи:",
        "default_punchline": "Лечь спать вовремя OR Сыграть ещё один цикл / бой"
    },
    {
        "name": "distracted_boyfriend",
        "title": "Distracted Boyfriend",
        "url": "https://i.imgflip.com/1ur9b0.jpg",
        "keywords": ["парень обернулся", "измена", "отвлекся"],
        "default_setup": "Когда у тебя есть проверенный надежный крафт...",
        "default_punchline": "Но в ангаре появилась новая безумная идея."
    }
]

# ----------------- WEB IMAGE FETCHER & SCRAPER -----------------

def fetch_image_from_url(url, dest_path, timeout=12):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        data = urllib.request.urlopen(req, timeout=timeout).read()
        with open(dest_path, "wb") as f:
            f.write(data)
        # Verify valid image
        im = Image.open(dest_path)
        im.verify()
        return True
    except Exception as e:
        if os.path.exists(dest_path):
            try: os.remove(dest_path)
            except Exception: pass
        return False

def search_internet_for_meme_image(query):
    """
    Ищет изображение для мема в интернете через Imgflip Memesearch, Wallhaven и DuckDuckGo.
    Возвращает локальный путь к скачанной картинке.
    """
    clean_q = re.sub(r"(?:найди|скинь|мем|мэм|про|с|бот|сделай|покажи|изучи|года|года|год)\s*", "", query, flags=re.I).strip()
    if not clean_q:
        clean_q = "funny gaming meme"

    cache_key = hashlib.md5(clean_q.encode()).hexdigest()[:10]
    cached_file = os.path.join(TEMPLATES_DIR, f"cached_{cache_key}.jpg")
    if os.path.exists(cached_file) and os.path.getsize(cached_file) > 1000:
        return cached_file

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1. Check curated list
    q_lower = clean_q.lower()
    for item in MEMES_2020_2022:
        if any(kw in q_lower for kw in item["keywords"]):
            if fetch_image_from_url(item["url"], cached_file):
                return cached_file

    # 2. Imgflip Meme Search
    try:
        url = f"https://imgflip.com/memesearch?q={urllib.parse.quote(clean_q)}"
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        matches = re.findall(r"src=[\x27\"]([^\x27\"]+\.jpg)[\x27\"]", html)
        for m in matches:
            img_code = re.search(r"/([a-z0-9]+)\.jpg", m)
            if img_code:
                full_url = f"https://i.imgflip.com/{img_code.group(1)}.jpg"
                if fetch_image_from_url(full_url, cached_file):
                    return cached_file
    except Exception as e:
        print(f"[MEME SEARCH] Imgflip search error: {e}")

    # 3. Wallhaven API (для артов, игр, персонажей, Махораги, Rain World, Crossout)
    try:
        wh_url = f"https://wallhaven.cc/api/v1/search?q={urllib.parse.quote(clean_q)}"
        req = urllib.request.Request(wh_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("data", [])
            if items:
                img_url = items[0].get("path")
                if img_url and fetch_image_from_url(img_url, cached_file):
                    return cached_file
    except Exception as e:
        print(f"[MEME SEARCH] Wallhaven error: {e}")

    # 4. DuckDuckGo Image scrape
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q + ' meme template high quality')}"
        req = urllib.request.Request(ddg_url, headers=headers)
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        imgs = re.findall(r"(https?://[^\s\"<>]+\.(?:jpg|jpeg|png))", html)
        for direct_url in imgs[:5]:
            if "icon" not in direct_url.lower() and fetch_image_from_url(direct_url, cached_file):
                return cached_file
    except Exception as e:
        print(f"[MEME SEARCH] DDG error: {e}")

    # 5. Fallback on any curated popular template
    fallback_tpl = random.choice(MEMES_2020_2022)
    if fetch_image_from_url(fallback_tpl["url"], cached_file):
        return cached_file

    return None

# ----------------- MEME STYLE RENDERERS -----------------

def render_caption_meme(base_img, text_top, text_bottom=None, sound_text=None):
    """
    СТИЛЬ 1: Современный чистый мем с белой карточкой-шапкой сверху (Twitter/Reddit/VK).
    """
    W, H = base_img.size
    target_w = 1000
    target_h = int(H * (target_w / W))
    base_resized = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    W, H = base_resized.size

    font_header = get_font("russo", 36)
    font_bottom = get_font("russo", 44)
    font_sound = get_font("russo", 32)

    # Calculate header height
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap_text(dummy_draw, text_top, font_header, W - 100)
    line_h = 46
    header_h = max(160, len(lines) * line_h + 80)
    sound_margin = 80 if sound_text else 0

    canvas_h = H + header_h + sound_margin
    canvas = Image.new("RGB", (W, canvas_h), (0, 0, 0))

    # White top card
    header_box = Image.new("RGB", (W, header_h), (255, 255, 255))
    canvas.paste(header_box, (0, 0))

    # Paste base image
    canvas.paste(base_resized, (0, header_h + sound_margin))

    draw = ImageDraw.Draw(canvas)

    # Draw top header text
    y_text = 40
    for l in lines:
        bb = draw.textbbox((0, 0), l, font=font_header)
        lw = bb[2] - bb[0]
        draw.text(((W - lw) // 2, y_text), l, font=font_header, fill=(15, 15, 15))
        y_text += line_h

    # Draw sound text if present
    if sound_text:
        sb = draw.textbbox((0, 0), sound_text, font=font_sound)
        sw = sb[2] - sb[0]
        draw_outlined_text(draw, ((W - sw) // 2, header_h + 20), sound_text, font_sound, fill="#FFD700", stroke_fill="#000000", stroke_width=4)

    # Draw bottom punchline if present
    if text_bottom:
        bot_lines = wrap_text(draw, text_bottom, font_bottom, W - 80)
        y_bot = canvas_h - (len(bot_lines) * 55 + 40)
        for bl in bot_lines:
            bb = draw.textbbox((0, 0), bl, font=font_bottom)
            bw = bb[2] - bb[0]
            draw_outlined_text(draw, ((W - bw) // 2, y_bot), bl, font=font_bottom, fill="#FFFFFF", stroke_fill="#000000", stroke_width=6)
            y_bot += 55

    return canvas

def render_demotivator(base_img, title, subtitle):
    """
    СТИЛЬ 2: Классический демотиватор (Черный фон, белая рамка, капс-заголовок, ироничный подтекст).
    """
    W, H = base_img.size
    target_w = 850
    target_h = int(H * (target_w / W))
    base_resized = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    W, H = base_resized.size

    margin_x = 75
    margin_top = 65
    bottom_space = 250

    canvas_w = W + margin_x * 2
    canvas_h = H + margin_top + bottom_space

    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    canvas.paste(base_resized, (margin_x, margin_top))

    draw = ImageDraw.Draw(canvas)

    # Double white frame
    frame_outer = [(margin_x - 12, margin_top - 12), (margin_x + W + 12, margin_top + H + 12)]
    frame_inner = [(margin_x - 8, margin_top - 8), (margin_x + W + 8, margin_top + H + 8)]
    draw.rectangle(frame_outer, outline="#FFFFFF", width=3)
    draw.rectangle(frame_inner, outline="#000000", width=2)

    font_title = get_font("bold", 54)
    font_sub = get_font("regular", 30)

    clean_title = title.upper()
    tb = draw.textbbox((0, 0), clean_title, font=font_title)
    tw = tb[2] - tb[0]
    draw.text(((canvas_w - tw) // 2, margin_top + H + 35), clean_title, font=font_title, fill="#FFFFFF")

    # Subtitle
    sub_lines = wrap_text(draw, subtitle, font_sub, canvas_w - 100)
    y_sub = margin_top + H + 115
    for sl in sub_lines:
        sb = draw.textbbox((0, 0), sl, font=font_sub)
        sw = sb[2] - sb[0]
        draw.text(((canvas_w - sw) // 2, y_sub), sl, font=font_sub, fill="#CCCCCC")
        y_sub += 40

    return canvas

def render_impact_meme(base_img, top_text, bottom_text):
    """
    СТИЛЬ 3: Классический вирусный Impact-мем (шрифт поверх изображения с мощной черной обводкой).
    """
    W, H = base_img.size
    target_w = 900
    target_h = int(H * (target_w / W))
    canvas = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    W, H = canvas.size

    draw = ImageDraw.Draw(canvas)
    font = get_font("impact", 50)

    # Top text
    if top_text:
        top_lines = wrap_text(draw, top_text.upper(), font, W - 60)
        y_top = 25
        for tl in top_lines:
            tb = draw.textbbox((0, 0), tl, font=font)
            tw = tb[2] - tb[0]
            draw_outlined_text(draw, ((W - tw) // 2, y_top), tl, font=font, fill="#FFFFFF", stroke_fill="#000000", stroke_width=6)
            y_top += 58

    # Bottom text
    if bottom_text:
        bot_lines = wrap_text(draw, bottom_text.upper(), font, W - 60)
        y_bot = H - (len(bot_lines) * 60 + 30)
        for bl in bot_lines:
            bb = draw.textbbox((0, 0), bl, font=font)
            bw = bb[2] - bb[0]
            draw_outlined_text(draw, ((W - bw) // 2, y_bot), bl, font=font, fill="#FFFFFF", stroke_fill="#000000", stroke_width=6)
            y_bot += 60

    return canvas

def render_breaking_news(base_img, title, news_text):
    """
    СТИЛЬ 4: Телевизионный выпуск «СРОЧНЫЕ НОВОСТИ / BREAKING NEWS».
    """
    W, H = base_img.size
    target_w = 960
    target_h = int(H * (target_w / W))
    canvas = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    W, H = canvas.size

    draw = ImageDraw.Draw(canvas)

    # Bottom news banner
    banner_h = 160
    banner_y = H - banner_h

    # Red tag box "СРОЧНЫЕ НОВОСТИ"
    draw.rectangle([(0, banner_y), (W, H)], fill=(20, 24, 34))
    draw.rectangle([(0, banner_y), (320, banner_y + 45)], fill="#DC2626")

    font_tag = get_font("russo", 24)
    font_live = get_font("bold", 22)
    font_main = get_font("bold", 34)
    font_ticker = get_font("regular", 24)

    draw.text((25, banner_y + 8), "🔴 СРОЧНЫЕ НОВОСТИ", font=font_tag, fill="#FFFFFF")
    draw.text((W - 130, banner_y + 10), "ПРЯМОЙ ЭФИР", font=font_live, fill="#EF4444")

    # Main news headline
    lines = wrap_text(draw, title, font_main, W - 60)
    if lines:
        draw.text((30, banner_y + 55), lines[0], font=font_main, fill="#FFFFFF")

    # Bottom yellow ticker
    draw.rectangle([(0, H - 38), (W, H)], fill="#FBBF24")
    ticker_str = f"⚡ В ПУСТОШАХ: {news_text} ⚡ ПОДРОБНОСТИ В СЛЕДУЮЩЕМ ВЫПУСКЕ..."
    draw.text((20, H - 32), ticker_str[:70], font=font_ticker, fill="#111827")

    return canvas

def render_tweet_post(base_img, author, text, likes_str="14.8K"):
    """
    СТИЛЬ 5: Твит / пост из соцсети с аватаркой, галочкой и прикрепленным мемом.
    """
    W, H = base_img.size
    target_w = 880
    target_h = int(H * (target_w / W))
    base_resized = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    W, H = base_resized.size

    font_author = get_font("bold", 30)
    font_handle = get_font("regular", 22)
    font_text = get_font("russo", 32)
    font_meta = get_font("regular", 22)

    dummy = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap_text(dummy, text, font_text, W - 40)
    header_h = 130 + len(lines) * 42

    canvas_w = W + 60
    canvas_h = header_h + H + 80
    canvas = Image.new("RGB", (canvas_w, canvas_h), (21, 32, 43)) # Twitter dark theme

    draw = ImageDraw.Draw(canvas)

    # Avatar circle
    draw.ellipse([(30, 25), (95, 90)], fill="#38BDF8")
    draw.text((48, 38), "🚜", font=get_font("russo", 34), fill="#FFFFFF")

    # Author & badge
    draw.text((115, 30), author, font=font_author, fill="#FFFFFF")
    draw.text((115, 65), f"@{author.lower().replace(' ', '_')} · 14 окт.", font=font_handle, fill="#8899A6")

    # Tweet text
    y_t = 110
    for l in lines:
        draw.text((35, y_t), l, font=font_text, fill="#FFFFFF")
        y_t += 42

    # Attached media with rounded border
    canvas.paste(base_resized, (30, header_h))
    draw.rectangle([(29, header_h - 1), (30 + W + 1, header_h + H + 1)], outline="#38444D", width=2)

    # Footer metrics
    footer_y = header_h + H + 25
    draw.text((35, footer_y), f"💬 421   🔁 1.2K   ❤️ {likes_str}   📊 89.4K", font=font_meta, fill="#8899A6")

    return canvas

def render_pov_meme(base_img, pov_text):
    """
    СТИЛЬ 6: POV / Жиза мем с кинематографичной полупрозрачной подписью.
    """
    W, H = base_img.size
    target_w = 900
    target_h = int(H * (target_w / W))
    canvas = base_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    W, H = canvas.size

    draw = ImageDraw.Draw(canvas)
    font_pov = get_font("russo", 40)

    clean_pov = pov_text if pov_text.upper().startswith("POV") or pov_text.upper().startswith("ЖИЗА") else f"POV: {pov_text}"
    lines = wrap_text(draw, clean_pov, font_pov, W - 80)
    banner_h = len(lines) * 52 + 50

    # Top dark overlay
    overlay = Image.new("RGBA", (W, banner_h), (0, 0, 0, 190))
    canvas.paste(overlay, (0, 0), overlay)

    y_p = 25
    for l in lines:
        bb = draw.textbbox((0, 0), l, font=font_pov)
        lw = bb[2] - bb[0]
        draw_outlined_text(draw, ((W - lw) // 2, y_p), l, font=font_pov, fill="#FFDD00", stroke_fill="#000000", stroke_width=4)
        y_p += 52

    return canvas

# ----------------- UNIVERSAL GENERATOR CONTROLLER -----------------

def clean_user_theme(raw_text):
    if not raw_text:
        return "Crossout Random"
    t = raw_text.strip()
    t = re.sub(r"(?:!бот|!bot|бот,|бот|пожалуйста|найди|скинь|сделай|сгенерируй|создай|покажи|мем|мэм|мемов|мэмов|про|с|на тему)\s*", "", t, flags=re.I).strip()
    return t or "Crossout Пустоши"

def generate_universal_meme(theme="", allow_repeat=False, recipient="yarik"):
    """
    Главная точка входа:
    1. Изучает тему и контекст (2020-2022, Махорага, Rain World, Crossout, учеба, жизнь).
    2. Ищет / скачивает в интернете реальное изображение/шаблон.
    3. Выбирает случайный разнообразный стиль (демотиватор, caption, impact, breaking news, tweet, pov).
    4. Сохраняет в локальную папку, PhotosEditor и синхронизирует.
    """
    clean_theme = clean_user_theme(theme)
    theme_lower = clean_theme.lower()

    # 1. Специфический запрос на мемы 2020-2022
    is_era_2020_2022 = any(y in theme_lower for y in ["2020", "2021", "2022"])
    
    # Check if Mahoraga
    is_mahoraga = any(w in theme_lower for w in ["махораг", "адаптир", "бог котор", "дхарма", "jujutsu"])

    # 2. Поиск картинки
    img_path = None
    curated_match = None

    if is_mahoraga:
        for m in MEMES_2020_2022:
            if m["name"] == "mahoraga":
                curated_match = m
                break
    elif is_era_2020_2022:
        # Выбираем случайный легендарный мем того периода!
        curated_match = random.choice([m for m in MEMES_2020_2022 if m["name"] != "mahoraga"])
    else:
        for m in MEMES_2020_2022:
            if any(kw in theme_lower for kw in m["keywords"]):
                curated_match = m
                break

    if curated_match:
        cached_tpl = os.path.join(TEMPLATES_DIR, f"{curated_match['name']}.jpg")
        if not os.path.exists(cached_tpl):
            fetch_image_from_url(curated_match["url"], cached_tpl)
        if os.path.exists(cached_tpl):
            img_path = cached_tpl

    if not img_path:
        # Ищем в интернете через скрапер
        img_path = search_internet_for_meme_image(clean_theme)

    # Загружаем изображение
    try:
        base_img = Image.open(img_path).convert("RGB")
    except Exception as e:
        print(f"[MEME ENGINE] Could not open image {img_path}: {e}")
        # Крайний fallback на локальный ассет
        fallback_assets = ["buff_doge_vs_cheems.png", "scav_large.png", "gasgen.png", "artificer.png"]
        chosen_fa = next((os.path.join(MEDIA_DIR, a) for a in fallback_assets if os.path.exists(os.path.join(MEDIA_DIR, a))), None)
        base_img = Image.open(chosen_fa).convert("RGB") if chosen_fa else Image.new("RGB", (800, 800), (20, 24, 32))

    # 3. Генерация юмора и текста через AI или креативные шаблоны
    prompt_ai = (
        f"Придумай угарный, жизненный интернет-мем на тему: «{clean_theme}».\n"
        "Ответь строго в JSON без разметки markdown:\n"
        "{\n"
        '  "style": "caption" (или "demotivator", "impact", "breaking_news", "tweet", "pov"),\n'
        '  "title": "Заголовок или верхний текст (1-2 строки)",\n'
        '  "subtitle": "Панчлайн, цитата или нижний текст",\n'
        '  "sound_or_extra": "Звуковой эффект или доп. реплика"\n'
        "}"
    )

    joke_data = None
    try:
        from keep_alive import run_antigravity_cli
        res_ai = run_antigravity_cli(prompt_ai)
        if res_ai:
            m = re.search(r"\{.*\}", res_ai, re.DOTALL)
            if m:
                joke_data = json.loads(m.group(0))
    except Exception:
        pass

    if not joke_data:
        # Fallback jokes depending on topic
        if curated_match:
            joke_data = {
                "style": random.choice(["caption", "demotivator", "impact"]),
                "title": curated_match["default_setup"],
                "subtitle": curated_match["default_punchline"],
                "sound_or_extra": "*ЩЁЛК* ☸️" if curated_match["name"] == "mahoraga" else None
            }
        elif is_mahoraga:
            joke_data = {
                "style": "caption",
                "title": "Когда жизнь пытается добить тебя очередным ударом, но забывает, сколько боли ты уже пережил:",
                "subtitle": "КОЛЕСО МАХОРАГИ СДЕЛАЛО ОБОРОТ. Я АДАПТИРОВАЛСЯ К ЛЮБОЙ БОЛИ.",
                "sound_or_extra": "*ЩЁЛК* — ЗВУК ВРАЩЕНИЯ КОЛЕСА ☸️"
            }
        else:
            styles_pool = ["demotivator", "caption", "impact", "breaking_news", "tweet", "pov"]
            chosen_st = random.choice(styles_pool)
            joke_data = {
                "style": chosen_st,
                "title": f"Когда зашел проверить {clean_theme}",
                "subtitle": "И понял, что к такому рандом тебя не готовил 💀",
                "sound_or_extra": None
            }

    style = joke_data.get("style", "caption").lower()
    t_top = joke_data.get("title", f"МЕМ: {clean_theme.upper()}")
    t_bot = joke_data.get("subtitle", "Классика жанра, которой нет объяснения")
    t_extra = joke_data.get("sound_or_extra")

    # 4. Рендеринг в выбранном стиле
    if style == "demotivator":
        result_img = render_demotivator(base_img, t_top, t_bot)
    elif style == "impact":
        result_img = render_impact_meme(base_img, t_top, t_bot)
    elif style == "breaking_news":
        result_img = render_breaking_news(base_img, t_top, t_bot)
    elif style == "tweet":
        result_img = render_tweet_post(base_img, "Ярик Пустоши", f"{t_top}\n{t_bot}")
    elif style == "pov":
        result_img = render_pov_meme(base_img, f"{t_top} {t_bot}")
    else: # caption
        result_img = render_caption_meme(base_img, t_top, t_bot, sound_text=t_extra)

    # 5. Сохранение
    file_id = int(time.time() * 1000) % 1000000
    out_filename = f"meme_{file_id}.jpg"
    out_path = os.path.join(MEDIA_DIR, out_filename)
    result_img.save(out_path, "JPEG", quality=92)

    # Save to PhotosEditor on Android
    if os.path.exists(ANDROID_PHOTOS_DIR):
        try:
            shutil.copy2(out_path, os.path.join(ANDROID_PHOTOS_DIR, out_filename))
        except Exception:
            pass

    # Save to saved_memes
    shutil.copy2(out_path, os.path.join(SAVED_MEMES_DIR, out_filename))

    # GDrive sync
    try:
        from gdrive import upload_file_to_drive
        upload_file_to_drive(out_path)
    except Exception:
        pass

    headline = f"[{style.upper()}] {t_top[:40]}"
    return out_path, headline
