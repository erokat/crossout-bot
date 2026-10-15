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
    russo_path = os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf")
    montserrat_path = os.path.join(MEDIA_DIR, "Montserrat.ttf")
    dejavu_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    dejavu_sans = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    font_map = {
        "russo": [
            russo_path,
            dejavu_bold,
            montserrat_path,
        ],
        "bold": [
            russo_path,
            dejavu_bold,
            montserrat_path,
        ],
        "impact": [
            russo_path,
            dejavu_bold,
            montserrat_path,
        ],
        "regular": [
            montserrat_path,
            dejavu_sans,
            russo_path,
        ]
    }
    candidates = font_map.get(name, font_map["russo"])
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                # Verify font can render Cyrillic 'А' without tofu
                bb_cyr = font.getbbox("А")
                bb_tofu = font.getbbox("\ufffe")
                if bb_cyr != bb_tofu:
                    return font
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

def clean_canvas_text(text):
    if not text:
        return ""
    # Strip emojis and non-renderable unicode characters
    emoji_pattern = re.compile(
        "["
        "\U00010000-\U0010ffff"
        "\u2600-\u27bf"
        "\u2300-\u23ff"
        "\u2b50-\u2b55"
        "\u3030\u303d\u3297\u3299\ufe0f"
        "]+",
        flags=re.UNICODE
    )
    t = emoji_pattern.sub("", str(text))
    t = re.sub(r"[🔴⚡💀🚜💥☸️👍🔥🎮🎯⭐❗❌✅⚠️]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def draw_outlined_text(draw, pos, text, font, fill="white", stroke_fill="black", stroke_width=4):
    x, y = pos
    safe_text = clean_canvas_text(text)
    draw.text((x, y), safe_text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)

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
        "name": "rain_world_slugcat",
        "title": "Rain World Slugcat",
        "url": "https://w.wallhaven.cc/full/3q/wallhaven-3qw86v.jpg",
        "keywords": ["рейн", "реин", "rain", "ворлд", "слизнец", "слизн", "вотчер", "watcher", "искусник", "артифисер"],
        "default_setup": "Когда в Rain World начался дождь, а ты застрял в трубе с ящерицей:",
        "default_punchline": "Конец очередного цикла выживания."
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
        "default_punchline": "Лечь спать вовремя ИЛИ Сыграть ещё один бой"
    },
    {
        "name": "distracted_boyfriend",
        "title": "Distracted Boyfriend",
        "url": "https://i.imgflip.com/1ur9b0.jpg",
        "keywords": ["парень обернулся", "измена", "отвлекся"],
        "default_setup": "Когда у тебя есть проверенный надежный крафт...",
        "default_punchline": "Но в ангаре появилась новая безумная идея."
    },
    {
        "name": "uganda_knuckles",
        "title": "Ugandan Knuckles 2018",
        "url": "https://i.imgflip.com/22bdq6.jpg",
        "keywords": ["2018", "уганда", "наклз", "knuckles", "do you know the way", "da way"],
        "default_setup": "КОГДА СПРАШИВАЮТ: «ТЫ ЗНАЕШЬ ПУТЬ?»",
        "default_punchline": "Когда выкатил утюг с дробовиками в рандом 2018 года."
    },
    {
        "name": "change_my_mind",
        "title": "Change My Mind 2018",
        "url": "https://i.imgflip.com/24y43o.jpg",
        "keywords": ["2018", "change my mind", "измени мое мнение", "стол", "crowder"],
        "default_setup": "Кроссаут 2018 года с утюгами и ховерами в космосе был легендарным.",
        "default_punchline": "Попробуй изменить моё мнение."
    },
    {
        "name": "is_this_a_pigeon",
        "title": "Is This A Pigeon 2018",
        "url": "https://i.imgflip.com/1o00in.jpg",
        "keywords": ["2018", "бабочка", "голубь", "is this a pigeon", "аниме"],
        "default_setup": "Игрок 2018 года видит крафт на ховерах на высоте 500 метров над картой:",
        "default_punchline": "«Это сбалансированная игра?»"
    },
    {
        "name": "grus_plan",
        "title": "Gru's Plan 2018",
        "url": "https://i.imgflip.com/26jxvz.jpg",
        "keywords": ["2018", "план грю", "грю", "доска", "презентация"],
        "default_setup": "1. Собираешь утюг. 2. Летишь в лоб врагу. 3. Сам переворачиваешься и взрываешься.",
        "default_punchline": "Сам переворачиваешься и взрываешься?!"
    },
    {
        "name": "roll_safe",
        "title": "Roll Safe Think About It",
        "url": "https://i.imgflip.com/1h7in3.jpg",
        "keywords": ["2018", "палец у виска", "умный парень", "roll safe", "подумай"],
        "default_setup": "Враги не смогут оторвать тебе оружие...",
        "default_punchline": "Если ты взорвешься на своем же Газгене в первую секунду!"
    }
]
CURATED_TEMPLATES = MEMES_2020_2022




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

def normalize_search_query_en(query):
    q = (query or "").lower().strip()
    if any(w in q for w in ["рейн", "реин", "rain", "ворлд", "слизн", "вотчер", "watcher", "искусник", "артифисер"]):
        return "rain world"
    if any(w in q for w in ["махораг", "адаптир", "дхарм"]):
        return "mahoraga jujutsu kaisen"
    if any(w in q for w in ["кросс", "крос", "crossout", "газген", "утюг", "ховер", "птур", "вереск", "скорп", "мамонт", "жнец", "автосборк"]):
        return "crossout game"
    if any(w in q for w in ["2018", "2019"]):
        return "crossout"
    if any(w in q for w in ["гигачад", "сигма", "gigachad"]):
        return "gigachad"
    if any(w in q for w in ["доге", "чимс", "doge", "cheems"]):
        return "doge cheems"
    if any(w in q for w in ["учеб", "сесси", "школ", "экзамен"]):
        return "tired student meme"
    clean_en = re.sub(r"[^\x00-\x7F]+", " ", q).strip()
    return clean_en if len(clean_en) > 3 else "gaming meme"

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
    # For Crossout memes, strictly use Crossout assets and clean templates. Never use scrapers that return Peter the Great or unrelated memes!
    if any(w in q_lower for w in ["кросс", "крос", "crossout", "газген", "утюг", "ховер", "птур", "вереск", "скорп", "мамонт", "жнец", "автосборк"]):
        xo_assets = ["ptur.png", "heather.png", "gasgen.png", "hover.png", "scorpion.png", "mammoth.png", "harvester.png"]
        existing = [os.path.join(MEDIA_DIR, a) for a in xo_assets if os.path.exists(os.path.join(MEDIA_DIR, a))]
        if existing:
            return random.choice(existing)

    for item in MEMES_2020_2022:
        if any(kw in q_lower for kw in item["keywords"]):
            if fetch_image_from_url(item["url"], cached_file):
                return cached_file

    # 2. Universal Yandex Image Search (supports ANY Russian or English query, finds exact memes, characters, games)
    try:
        yandex_q = f"{clean_q} мем шаблон" if "мем" not in clean_q.lower() else clean_q
        y_url = f"https://yandex.ru/images/search?text={urllib.parse.quote(yandex_q)}"
        req = urllib.request.Request(y_url, headers=headers)
        with urllib.request.urlopen(req, timeout=7) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            raw_imgs = re.findall(r"img_url=([^\x26\s\"<>]+)", html)
            for raw_u in raw_imgs[:6]:
                unq = urllib.parse.unquote(raw_u)
                if any(ext in unq.lower() for ext in [".jpg", ".png", ".jpeg"]):
                    if fetch_image_from_url(unq, cached_file):
                        return cached_file
    except Exception as e:
        print(f"[MEME SEARCH] Yandex search error: {e}")

    # 3. Wallhaven API with normalized English query
    en_query = normalize_search_query_en(clean_q)
    try:
        wh_url = f"https://wallhaven.cc/api/v1/search?q={urllib.parse.quote(en_query)}"
        req = urllib.request.Request(wh_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("data", [])
            if items:
                img_url = items[0].get("path")
                if img_url and fetch_image_from_url(img_url, cached_file):
                    return cached_file
    except Exception as e:
        print(f"[MEME SEARCH] Wallhaven error: {e}")

    # 4. Imgflip Meme Search
    try:
        url = f"https://imgflip.com/memesearch?q={urllib.parse.quote(en_query)}"
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

    # 4. DuckDuckGo Image scrape
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(en_query + ' meme template high quality')}"
        req = urllib.request.Request(ddg_url, headers=headers)
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        imgs = re.findall(r"(https?://[^\s\"<>]+\.(?:jpg|jpeg|png))", html)
        for direct_url in imgs[:5]:
            if "icon" not in direct_url.lower() and fetch_image_from_url(direct_url, cached_file):
                return cached_file
    except Exception as e:
        print(f"[MEME SEARCH] DDG error: {e}")

    # 5. Topic-Specific Local or Curated Fallbacks
    if any(w in q_lower for w in ["рейн", "реин", "rain", "ворлд", "слизн", "вотчер", "watcher", "искусник"]):
        rw_candidates = ["artificer.png", "scav_large.png"]
        for c in rw_candidates:
            p = os.path.join(MEDIA_DIR, c)
            if os.path.exists(p):
                return p
        if fetch_image_from_url("https://w.wallhaven.cc/full/3q/wallhaven-3qw86v.jpg", cached_file):
            return cached_file

    if any(w in q_lower for w in ["махораг", "адаптир", "дхарм"]):
        mh_path = os.path.join(TEMPLATES_DIR, "mahoraga.jpg")
        if os.path.exists(mh_path):
            return mh_path

    # Clean curated list without trade_offer
    clean_templates = [m for m in MEMES_2020_2022 if m["name"] not in ["trade_offer"]]
    if clean_templates:
        fallback_tpl = random.choice(clean_templates)
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

    font_header = get_font("russo", 36)
    font_bottom = get_font("russo", 44)
    font_sound = get_font("russo", 32)

    # Calculate header height
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap_text(dummy_draw, text_top, font_header, target_w - 100)
    line_h = 46
    header_h = max(160, len(lines) * line_h + 80)
    sound_lines = wrap_text(dummy_draw, sound_text, font_sound, target_w - 60) if sound_text else []
    sound_margin = max(70, len(sound_lines) * 40 + 20) if sound_text else 0

    # Ensure total height does not exceed safe preview limit (1200px)
    max_safe_h = 1200
    avail_img_h = max_safe_h - header_h - sound_margin
    scale = min(target_w / W, avail_img_h / H) if (H * (target_w / W) > avail_img_h) else (target_w / W)
    new_w = max(300, int(W * scale))
    new_h = max(300, int(H * scale))
    base_resized = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas_w = max(new_w, target_w)
    canvas_h = new_h + header_h + sound_margin
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))

    # White top card
    header_box = Image.new("RGB", (canvas_w, header_h), (255, 255, 255))
    canvas.paste(header_box, (0, 0))

    # Paste base image centered
    offset_x = (canvas_w - new_w) // 2
    canvas.paste(base_resized, (offset_x, header_h + sound_margin))

    draw = ImageDraw.Draw(canvas)

    # Draw top header text
    y_text = 40
    for l in lines:
        bb = draw.textbbox((0, 0), l, font=font_header)
        lw = bb[2] - bb[0]
        lx = (canvas_w - lw) // 2 - bb[0]
        draw.text((lx, y_text), l, font=font_header, fill=(15, 15, 15))
        y_text += line_h

    # Draw sound text if present
    if sound_text:
        y_sound = header_h + 12
        for sl in sound_lines:
            sb = draw.textbbox((0, 0), sl, font=font_sound)
            sw = sb[2] - sb[0]
            sx = (canvas_w - sw) // 2 - sb[0]
            draw_outlined_text(draw, (sx, y_sound), sl, font=font_sound, fill="#FFD700", stroke_fill="#000000", stroke_width=4)
            y_sound += 38

    # Draw bottom punchline if present
    if text_bottom:
        bot_lines = wrap_text(draw, text_bottom, font_bottom, canvas_w - 80)
        y_bot = canvas_h - (len(bot_lines) * 55 + 40)
        for bl in bot_lines:
            bb = draw.textbbox((0, 0), bl, font=font_bottom)
            bw = bb[2] - bb[0]
            bx = (canvas_w - bw) // 2 - bb[0]
            draw_outlined_text(draw, (bx, y_bot), bl, font=font_bottom, fill="#FFFFFF", stroke_fill="#000000", stroke_width=6)
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
    title = clean_canvas_text(title)
    news_text = clean_canvas_text(news_text)

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

    draw.text((25, banner_y + 8), "СРОЧНЫЕ НОВОСТИ", font=font_tag, fill="#FFFFFF")
    draw.text((W - 145, banner_y + 10), "ПРЯМОЙ ЭФИР", font=font_live, fill="#EF4444")

    # Main news headline
    lines = wrap_text(draw, title, font_main, W - 60)
    if lines:
        draw.text((30, banner_y + 55), lines[0], font=font_main, fill="#FFFFFF")

    # Bottom yellow ticker
    draw.rectangle([(0, H - 38), (W, H)], fill="#FBBF24")
    ticker_str = f"В ПУСТОШАХ: {news_text} | ПОДРОБНОСТИ В СЛЕДУЮЩЕМ ВЫПУСКЕ..."
    draw.text((20, H - 32), ticker_str[:75], font=font_ticker, fill="#111827")

    return canvas

def render_tweet_post(base_img, author, text, likes_str="14.8K"):
    """
    СТИЛЬ 5: Твит / пост из соцсети с аватаркой, галочкой и прикрепленным мемом.
    """
    author = clean_canvas_text(author)
    text = clean_canvas_text(text)

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

    # Avatar circle with text badge
    draw.ellipse([(30, 25), (95, 90)], fill="#38BDF8")
    draw.text((45, 38), "CR", font=get_font("russo", 34), fill="#FFFFFF")

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
    footer_text = f"Ответов: 421   Репостов: 1.2K   Лайков: {likes_str}"
    draw.text((35, footer_y), footer_text, font=font_meta, fill="#8899A6")

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
        return "Crossout"
    t = raw_text.strip()

    # Strip bot call
    t = re.sub(r"^(?:!бот|!bot|бот[,:]?)\s*", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:пожалуйста|плиз|эй|ну-ка|давай|слышь)\s*", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:сделай|скинь|создай|сгенерируй|нарисуй|покажи|выдай|запили|намути|придумай|дай)\s*", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:мне|нам|ярику|мише|быстро|срочно|еще|один|парочку)\s*", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:мемчик|мемасик|мем|мэм|мемов|мэмов|картинку|пикчу|шутку|прикол)\s*", "", t, flags=re.I).strip()

    # Strip prepositions & broken fragments
    t = re.sub(r"^(?:про|с|на тему|по теме|по игре|по|из|в|о|об)\s*", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:кросаута|кроссаута|crossout)\s+(?:того\s+что\s+там\s+было\s+в|того\s+что\s+было\s+в|того\s+что\s+было|как\s+было\s+в|в)\s*", "Crossout ", t, flags=re.I).strip()
    t = re.sub(r"^(?:того\s+что\s+там\s+было\s+в|того\s+что\s+было\s+в|того\s+что\s+было|как\s+было\s+в)\s*", "", t, flags=re.I).strip()
    t = re.sub(r"^(?:про то как|про то что|как)\s*", "", t, flags=re.I).strip()

    # Rain World typo & topic normalization
    t = re.sub(r"\bодин\s+ворлд\w*\b", "Rain World", t, flags=re.I)
    t = re.sub(r"\bрейн\s*ворлд\w*\b", "Rain World", t, flags=re.I)
    t = re.sub(r"\bреин\s*ворлд\w*\b", "Rain World", t, flags=re.I)

    # Normalize year phrasing
    t = re.sub(r"\b(201[5-9]|202[0-6])\s*году\b", r"\1 года", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()

    years = re.findall(r"\b(201[5-9]|202[0-6])\b", t)
    year_str = years[0] if years else None

    if not t or t.lower() in ["того", "там", "было", "что", "это", "как", "года"]:
        if year_str:
            return f"Crossout {year_str} года"
        return "Crossout"
    return t

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

    # 1. Специфический запрос на мемы определенных эпох
    is_era_2018 = "2018" in theme_lower
    is_era_2019 = "2019" in theme_lower
    is_era_2020_2022 = any(y in theme_lower for y in ["2020", "2021", "2022"])
    
    # Check if Mahoraga
    is_mahoraga = any(w in theme_lower for w in ["махораг", "адаптир", "бог котор", "дхарма", "jujutsu"])
    is_rainworld = any(w in theme_lower for w in ["рейн", "реин", "rain", "слизнец", "слизн", "ворлд", "вотчер", "watcher", "искусник", "артифисер", "карм", "пебблс"])

    # 2. Поиск картинки
    img_path = None
    curated_match = None

    if is_mahoraga:
        for m in CURATED_TEMPLATES:
            if m["name"] == "mahoraga":
                curated_match = m
                break
    elif is_era_2018:
        # Случайный легендарный мем 2018 года! (Uganda Knuckles, Change My Mind, Gru Plan, Pigeon, Roll Safe)
        candidates_2018 = [m for m in CURATED_TEMPLATES if "2018" in m.get("keywords", [])]
        if candidates_2018:
            curated_match = random.choice(candidates_2018)
    elif is_era_2020_2022:
        # Случайный легендарный мем 2020-2022 периода!
        candidates_era = [m for m in CURATED_TEMPLATES if any(y in m.get("keywords", []) for y in ["2020", "2021", "2022"]) and m["name"] != "mahoraga"]
        if candidates_era:
            curated_match = random.choice(candidates_era)
    else:
        for m in CURATED_TEMPLATES:
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
        is_xo = any(w in theme_lower for w in ["кросс", "крос", "crossout", "газген", "утюг", "ховер", "крафт", "бочки", "рандом", "пустош", "вереск", "птур", "кларнет", "скорп", "мамонт", "жнец", "дробовик", "тошнитель", "реликт", "билды", "билд", "оружие", "автосборк"])
        if is_xo:
            xo_assets = ["ptur.png", "heather.png", "gasgen.png", "hover.png", "scorpion.png", "mammoth.png", "harvester.png", "meme_autobuild.png", "buff_doge_vs_cheems.png"]
            existing = [os.path.join(MEDIA_DIR, a) for a in xo_assets if os.path.exists(os.path.join(MEDIA_DIR, a))]
            if existing:
                img_path = random.choice(existing)
            else:
                clean_tpls = [m for m in CURATED_TEMPLATES if m["name"] in ["doge_vs_cheems", "gigachad", "two_buttons", "distracted_boyfriend", "grus_plan", "change_my_mind"]]
                if clean_tpls:
                    m = random.choice(clean_tpls)
                    img_path = os.path.join(TEMPLATES_DIR, f"{m['name']}.jpg")
        else:
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
        "СТРОЖАЙШЕЕ ТРЕБОВАНИЕ: ВСЕ ТЕКСТЫ ДОЛЖНЫ БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ! НИКАКОГО АНГЛИЙСКОГО!\n"
        "Ответь строго в JSON без разметки markdown:\n"
        "{\n"
        '  "style": "caption" (или "demotivator", "impact", "breaking_news", "tweet", "pov"),\n'
        '  "title": "Заголовок или верхний текст строго на русском (1-2 строки)",\n'
        '  "subtitle": "Панчлайн, цитата или нижний текст строго на русском",\n'
        '  "sound_or_extra": "Звуковой эффект или доп. реплика на русском"\n'
        "}"
    )

    joke_data = None
    try:
        from keep_alive import ask_ai, run_antigravity_cli
        res_ai = ask_ai(prompt_ai) or run_antigravity_cli(prompt_ai)
        if res_ai:
            m = re.search(r"\{.*\}", res_ai, re.DOTALL)
            if m:
                joke_data = json.loads(m.group(0))
    except Exception:
        pass

    if not joke_data:
        # Fallback jokes depending on topic - rich, varied, 100% Russian and grammatically sound
        if curated_match and curated_match.get("default_setup"):
            joke_data = {
                "style": random.choice(["caption", "demotivator", "impact"]),
                "title": curated_match["default_setup"],
                "subtitle": curated_match["default_punchline"],
                "sound_or_extra": "*ЩЁЛК*" if curated_match["name"] == "mahoraga" else None
            }
        elif is_era_2018:
            jokes_2018 = [
                {
                    "style": "caption",
                    "title": "Игроки в Crossout в 2018 году:",
                    "subtitle": "«Ничего, сейчас нафармлю меди, скрафчу бочки и жизнь наладится!»",
                    "sound_or_extra": None
                },
                {
                    "style": "demotivator",
                    "title": "МЕТА 2018 ГОДА",
                    "subtitle": "Когда ховеры летали в стратосферу, а утюги ломали законы физики",
                    "sound_or_extra": None
                },
                {
                    "style": "impact",
                    "title": "ПОМНИШЬ 2018 ГОД В ПУСТОШАХ?",
                    "subtitle": "КОГДА ОДИН ВАНШОТ РЕШАЛ ИСХОД ВСЕГО БОЯ",
                    "sound_or_extra": None
                },
                {
                    "style": "breaking_news",
                    "title": "АРХИВЫ ПУСТОШЕЙ 2018 ГОДА",
                    "subtitle": "Утюги с дробовиками признаны самым опасным явлением",
                    "sound_or_extra": None
                }
            ]
            joke_data = random.choice(jokes_2018)
        elif is_era_2019:
            jokes_2019 = [
                {
                    "style": "caption",
                    "title": "Игроки в Crossout в 2019 году:",
                    "subtitle": "Когда думал, что познал дзен, но вышел очередной балансный патч",
                    "sound_or_extra": None
                },
                {
                    "style": "demotivator",
                    "title": "CROSSOUT 2019",
                    "subtitle": "Каждый бой как последняя битва за выживание в Пустошах",
                    "sound_or_extra": None
                },
                {
                    "style": "impact",
                    "title": "ВЫЕХАЛ В РАНДОМ 2019 ГОДА",
                    "subtitle": "ИНЖЕНЕРНАЯ МЫСЛЬ ЗАШЛА СЛИШКОМ ДАЛЕКО",
                    "sound_or_extra": None
                }
            ]
            joke_data = random.choice(jokes_2019)
        elif is_mahoraga:
            jokes_mahoraga = [
                {
                    "style": "caption",
                    "title": "Когда рандом пытается сломать меня очередным поражением:",
                    "subtitle": "КОЛЕСО МАХОРАГИ СДЕЛАЛО ОБОРОТ. Я АДАПТИРОВАЛСЯ К ЛЮБОЙ БОЛИ.",
                    "sound_or_extra": "*ЩЁЛК* — ЗВУК ВРАЩЕНИЯ КОЛЕСА"
                },
                {
                    "style": "caption",
                    "title": "Когда вражеский клан взял токсичные мета-сборки:",
                    "subtitle": "КОЛЕСО УЖЕ ПОВЕРНУЛОСЬ. ТЕПЕРЬ Я ЗНАЮ ВСЕ ИХ СЛАБЫЕ МЕСТА.",
                    "sound_or_extra": "*ЩЁЛК* — АДАПТАЦИЯ ЗАВЕРШЕНА"
                },
                {
                    "style": "demotivator",
                    "title": "БОГ АДАПТАЦИИ",
                    "subtitle": "Любой урон и поражение делают меня только сильнее",
                    "sound_or_extra": None
                }
            ]
            joke_data = random.choice(jokes_mahoraga)
        elif is_rainworld:
            jokes_rw = [
                {
                    "style": "caption",
                    "title": "Слизнец, когда до дождя осталось 10 секунд, а убежище закрыто:",
                    "subtitle": "Суровые законы выживания в Rain World не знают пощады",
                    "sound_or_extra": None
                },
                {
                    "style": "caption",
                    "title": "Когда анонсировали Rain World: The Watcher:",
                    "subtitle": "Готовимся страдать в новых регионах и умирать от дождя по 50 раз за цикл",
                    "sound_or_extra": None
                },
                {
                    "style": "demotivator",
                    "title": "THE WATCHER",
                    "subtitle": "Новое DLC, старая добрая боль и бесконечная борьба за выживание",
                    "sound_or_extra": None
                }
            ]
            joke_data = random.choice(jokes_rw)
        else:
            is_heather_ptur = ("вереск" in theme_lower) and ("птур" in theme_lower or "ракета" in theme_lower or "кларнет" in theme_lower)
            is_xo_topic = is_heather_ptur or any(w in theme_lower for w in [
                "кросс", "крос", "crossout", "газген", "утюг", "ховер", "крафт",
                "бочки", "рандом", "пустош", "вереск", "птур", "кларнет",
                "скорп", "мамонт", "жнец", "дробовик", "тошнитель", "реликт"
            ])
            if is_heather_ptur:
                jokes_target = [
                    {
                        "style": "caption",
                        "title": "Геймплей на Вереске vs Геймплей на ПТУРе в Crossout:",
                        "subtitle": "Стреляешь навесом на удачу через полкарты vs 10 секунд ведешь ракету, пока твой крафт сзади разбирают на винтики 💀",
                        "sound_or_extra": None
                    },
                    {
                        "style": "demotivator",
                        "title": "ВЕРЕСК VS ПТУР",
                        "subtitle": "Один жмет ЛКМ и надеется на рандом, второй смотрит кино от первого лица до первого забора",
                        "sound_or_extra": None
                    },
                    {
                        "style": "impact",
                        "title": "ВЕРЕСК: ЗАПУСТИЛ И ЗАБЫЛ",
                        "subtitle": "ПТУР: ВЕЛ РАКЕТУ 15 СЕКУНД И ВРЕЗАЛСЯ В ТРУБУ СОЮЗНИКА",
                        "sound_or_extra": None
                    },
                    {
                        "style": "pov",
                        "title": "ЖИЗА: Момент сравнения геймплея миномета Вереск и ПТУРа",
                        "subtitle": "На Вереске ты бог баллистики, на ПТУРе — оператор дрона-камикадзе в гараже",
                        "sound_or_extra": None
                    }
                ]
            elif is_xo_topic:
                jokes_target = [
                    {
                        "style": "caption",
                        "title": "Мой билд в гараже после 3 часов настройки углов стрельбы:",
                        "subtitle": "В первом же бою Газген сдетонировал от случайной пульки бота",
                        "sound_or_extra": None
                    },
                    {
                        "style": "demotivator",
                        "title": "БАЛАНС В ПУСТОШАХ",
                        "subtitle": "Существует ровно до тех пор, пока ты не нажал кнопку «В бой»",
                        "sound_or_extra": None
                    },
                    {
                        "style": "impact",
                        "title": "СОБРАЛ КРАФТ ПО СОВЕТАМ ИЗ ЧАТА",
                        "subtitle": "ПЕРВЫЙ ЖЕ БОТ С ДРОБОВИКАМИ РАЗОБРАЛ ЕГО НА ВИНТИКИ",
                        "sound_or_extra": None
                    },
                    {
                        "style": "caption",
                        "title": "Когда тиммейт уверенно кричит в войс: «Я прикрою!»:",
                        "subtitle": "И через 3 секунды ты наблюдаешь только его горящую кабину",
                        "sound_or_extra": None
                    },
                    {
                        "style": "demotivator",
                        "title": "ГЕНЕРАТОР ГАЗГЕН",
                        "subtitle": "Самое надежное средство быстрой телепортации в ангар",
                        "sound_or_extra": None
                    },
                    {
                        "style": "pov",
                        "title": "ЖИЗА: Выехал в бой на красивом неповоротливом крафте",
                        "subtitle": "А навстречу несутся 4 утюга со скоростью 120 км/ч",
                        "sound_or_extra": None
                    }
                ]
            else:
                jokes_target = [
                    {
                        "style": "caption",
                        "title": f"Когда думал, что {clean_theme} — это просто и понятно:",
                        "subtitle": "Реальность через 5 минут: полное непонимание происходящего 💀",
                        "sound_or_extra": None
                    },
                    {
                        "style": "demotivator",
                        "title": clean_theme.upper(),
                        "subtitle": "То, к чему жизнь определенно тебя не готовила",
                        "sound_or_extra": None
                    },
                    {
                        "style": "pov",
                        "title": f"ЖИЗА: Мое лицо в любой ситуации, когда речь заходит про {clean_theme}",
                        "subtitle": "",
                        "sound_or_extra": None
                    },
                    {
                        "style": "caption",
                        "title": f"План на день: идеально разобраться с темой «{clean_theme}»",
                        "subtitle": "Суровая реальность: ничего не понял, но очень интересно 🔥",
                        "sound_or_extra": None
                    },
                    {
                        "style": "impact",
                        "title": f"ЗАШЕЛ ИЗУЧИТЬ {clean_theme.upper()}",
                        "subtitle": "ВЫШЕЛ С НОВОЙ ПСИХОЛОГИЧЕСКОЙ ТРАВМОЙ",
                        "sound_or_extra": None
                    }
                ]
            joke_data = random.choice(jokes_target)

    style = joke_data.get("style", "caption").lower()
    t_top = joke_data.get("title", f"МЕМ: {clean_theme.upper()}")
    t_bot = joke_data.get("subtitle", "Классика жанра, которой нет объяснения")
    t_extra = joke_data.get("sound_or_extra")
    # Enforce style compatibility so styles look natural with the image
    img_path_str = str(img_path).lower() if img_path else ""
    if "gigachad" in img_path_str or (curated_match and curated_match.get("name") in ["gigachad", "roll_safe", "is_this_a_pigeon", "bernie_sanders"]):
        if style in ["breaking_news", "tweet"]:
            style = "demotivator" if random.random() < 0.5 else "caption"

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
