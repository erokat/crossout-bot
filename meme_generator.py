import os
import random
import time
import hashlib
import shutil
from PIL import Image, ImageDraw, ImageFont

from config import MEDIA_DIR, SAVED_MEMES_DIR
from db import is_meme_already_sent, record_sent_meme, get_last_sent_meme

def get_font(size):
    font_paths = [
        os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
        os.path.join(MEDIA_DIR, "RobotoCondensed-Bold.ttf"),
        os.path.join(MEDIA_DIR, "Anton.ttf"),
        os.path.join(MEDIA_DIR, "Comfortaa.ttf"),
        os.path.join(MEDIA_DIR, "Oswald.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_text_with_outline(draw, pos, text, font, fill="white", outline="black", outline_width=3):
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)

def get_asset(name):
    p = os.path.join(MEDIA_DIR, name)
    return p if os.path.exists(p) else None

# --- GENERATOR FUNCTIONS (each returns img, template_name, headline) ---

def gen_rw_crossover_1():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 20, 28))
    draw = ImageDraw.Draw(img)
    headline = "RAIN WORLD × CROSSOUT: ВЗРЫВНОЕ КОПЬЕ VS ГАЗГЕН"
    
    draw_text_with_outline(draw, (45, 35), "RAIN WORLD  ×  CROSSOUT", get_font(38), fill="#00FFCC")
    draw.line([(40, 85), (860, 85)], fill="#555555", width=3)
    draw_text_with_outline(draw, (50, 105), "Когда Слизнекот и Скэвы случайно заехали в Пустоши...", get_font(24), fill="#E2E8F0")

    scav = get_asset("scav_large.png")
    if scav:
        im = Image.open(scav).convert("RGBA").resize((280, 280))
        img.paste(im, (60, 160), im)
    draw_text_with_outline(draw, (60, 460), "1. Скэв кинул взрывное копье", get_font(28), fill="#FFCC00")

    draw_text_with_outline(draw, (410, 270), "⚡ VS ⚡", get_font(36), fill="#FF3333")

    gas = get_asset("gasgen.png")
    if gas:
        im = Image.open(gas).convert("RGBA").resize((260, 260))
        img.paste(im, (540, 170), im)
    draw_text_with_outline(draw, (500, 460), "2. Попал в открытый Газген", get_font(28), fill="#FF4444")

    draw.rectangle([(40, 520), (860, 780)], fill=(28, 32, 46), outline="#FF3333", width=2)
    draw_text_with_outline(draw, (65, 545), "💥 ДЕТОНАЦИЯ СИЛОЙ В 100 МЕГАТОНН 💥", get_font(36), fill="#FF2222")
    draw_text_with_outline(draw, (70, 610), "• Цикл в Rain World мгновенно завершен", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 660), "• В Crossout: крафт улетел в ангар до конца боя", get_font(26), fill="#FFCC00")
    draw_text_with_outline(draw, (70, 715), "• Дождь испарился вместе с локацией 💀", get_font(26), fill="#AAAAAA")

    draw_text_with_outline(draw, (120, 820), "«Ярик, оцени этот кроссовер от 1 до 10!»", get_font(34), fill="#38BDF8")
    return img, "rw_crossover_1", headline

def gen_rw_crossover_2():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(14, 18, 30))
    draw = ImageDraw.Draw(img)
    headline = "СЛИЗНЕКОТ ЗА РУЛЕМ ХОВЕРА В ПУСТОШАХ"

    draw_text_with_outline(draw, (60, 40), "СЛИЗНЕКОТ В ПУСТОШАХ CROSSOUT", get_font(36), fill="#38BDF8")
    draw.line([(40, 90), (860, 90)], fill="#444444", width=3)
    draw_text_with_outline(draw, (50, 110), "«Думал, что ящеры и дождь опасны...»", get_font(24), fill="#94A3B8")

    art = get_asset("artificer.png") or get_asset("scav_large.png")
    if art:
        im = Image.open(art).convert("RGBA").resize((260, 260))
        img.paste(im, (80, 170), im)

    hov = get_asset("hover.png") or get_asset("kapkan.png")
    if hov:
        im = Image.open(hov).convert("RGBA").resize((280, 240))
        img.paste(im, (520, 180), im)

    draw_text_with_outline(draw, (60, 450), "Собрал крафт на 4 ховерах", get_font(28), fill="#4ADE80")
    draw_text_with_outline(draw, (500, 450), "Поставил Капкан и ПТУР", get_font(28), fill="#F87171")

    draw.rectangle([(40, 520), (860, 770)], fill=(24, 28, 44), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (70, 550), "РЕАЛЬНОСТЬ ПЕРВОГО БОЯ:", get_font(32), fill="#FBBF24")
    draw_text_with_outline(draw, (70, 610), "1. Зацепился ховером за мусорный бак", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 660), "2. Сзади на полной скорости въехал дробовод", get_font(26), fill="#FF6B6B")
    draw_text_with_outline(draw, (70, 715), "3. Вернулся в убежище Rain World быстрее дождя", get_font(26), fill="#93C5FD")

    draw_text_with_outline(draw, (140, 810), "«Пустоши похуже любого Затененного Цитаделя»", get_font(28), fill="#E2E8F0")
    return img, "rw_crossover_2", headline

def gen_autobuild():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(20, 22, 28))
    draw = ImageDraw.Draw(img)
    headline = "АВТОСБОРКА В CROSSOUT: ШЕДЕВР ИНЖЕНЕРИИ"

    draw_text_with_outline(draw, (50, 40), "АВТОСБОРКА В CROSSOUT:", get_font(38), fill="#FFCC00")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (50, 130), "Ожидание: идеальный сбалансированный крафт", get_font(28), fill="#00FFCC")
    draw_text_with_outline(draw, (50, 180), "Реальность:", get_font(28), fill="#FF4444")

    gas = get_asset("gasgen.png")
    if gas:
        g = Image.open(gas).convert("RGBA").resize((280, 280))
        img.paste(g, (100, 250), g)
        draw_text_with_outline(draw, (80, 550), "Газген на бампере", get_font(26))

    pt = get_asset("ptur.png")
    if pt:
        p = Image.open(pt).convert("RGBA").resize((320, 260))
        img.paste(p, (480, 260), p)
        draw_text_with_outline(draw, (490, 550), "ПТУР в лоб кабине", get_font(26))

    draw_text_with_outline(draw, (60, 680), "⚠️ ПЕРЕГРУЗ: +6500 КГ | СКОРОСТЬ: 3 КМ/Ч", get_font(34), fill="#FF2222")
    draw_text_with_outline(draw, (180, 760), "«Шедевр инженерной мысли»", get_font(28), fill="#CCCCCC")
    return img, "autobuild", headline

def gen_gasgen_blast():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(28, 18, 18))
    draw = ImageDraw.Draw(img)
    headline = "ПОСТАВИЛ ГАЗГЕН В ПУСТОШАХ НА ПЕРВОЙ СЕКУНДЕ"

    draw_text_with_outline(draw, (80, 40), "ПОСТАВИЛ ГАЗГЕН В ПУСТОШАХ", get_font(38), fill="#FF3333")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "1. Заспавнился в бою с хорошим настроением", get_font(28))

    gas = get_asset("gasgen.png")
    if gas:
        g = Image.open(gas).convert("RGBA").resize((320, 320))
        img.paste(g, (290, 220), g)

    draw_text_with_outline(draw, (60, 580), "2. Шальная пуля коснулась заднего брызговика", get_font(28), fill="#FFCC00")
    draw_text_with_outline(draw, (100, 670), "💥 ВЗРЫВ СИЛОЙ 10 МЕГАТОНН 💥", get_font(36), fill="#FF2222")
    draw_text_with_outline(draw, (210, 760), "«Ушел в ангар на 5-й секунде боя»", get_font(28), fill="#AAAAAA")
    return img, "gasgen_blast", headline

def gen_ptur_sniper():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 24, 30))
    draw = ImageDraw.Draw(img)
    headline = "ТИПИЧНЫЙ ПТУРОВОД ЗА ХОЛМОМ В ИНВИЗЕ"

    draw_text_with_outline(draw, (120, 40), "ТИПИЧНЫЙ ПТУРОВОД В БОЮ", get_font(38), fill="#00CCFF")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Стоит за холмом в инвизе 3 минуты и выцеливает...", get_font(26))

    pt = get_asset("ptur.png")
    if pt:
        p = Image.open(pt).convert("RGBA").resize((380, 300))
        img.paste(p, (260, 220), p)

    draw_text_with_outline(draw, (60, 580), "Запускает управляемую ракету через всю карту 🚀", get_font(28), fill="#FFFF44")
    draw_text_with_outline(draw, (70, 670), "Итог: ракета врезалась в свой же дрон 😂", get_font(34), fill="#FF4444")
    draw_text_with_outline(draw, (260, 760), "«Снайпер года в Пустошах»", get_font(28), fill="#888888")
    return img, "ptur_sniper", headline

def gen_scorpion_relic():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(20, 24, 32))
    draw = ImageDraw.Draw(img)
    headline = "РЕЛИКТОВЫЙ НАГИБ: СКОРПИОН ЗА 80K МОНЕТ"

    draw_text_with_outline(draw, (80, 40), "РЕЛИКТОВЫЙ НАГИБ: СКОРПИОН", get_font(38), fill="#38BDF8")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Продал почку, почку друга и гараж ради двух Скорпов...", get_font(24))

    sc = get_asset("scorpion.png")
    if sc:
        s = Image.open(sc).convert("RGBA").resize((380, 280))
        img.paste(s, (260, 210), s)

    draw_text_with_outline(draw, (60, 560), "Первый залп в бою:", get_font(28), fill="#FFCC00")
    draw_text_with_outline(draw, (50, 630), "Снаряд пробил 15 деталей и выбил фару боту на 15 урона 😂", get_font(30), fill="#FF4444")
    draw_text_with_outline(draw, (160, 740), "«Зато статус в Пустошах легендарный»", get_font(28), fill="#AAAAAA")
    return img, "scorpion_relic", headline

def gen_mammoth_tank():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(26, 22, 18))
    draw = ImageDraw.Draw(img)
    headline = "МАМОНТОВЫЙ ТЯЖ НА 25 ТОНН В РАНДОМЕ"

    draw_text_with_outline(draw, (80, 40), "МАМОНТОВЫЙ ТЯЖ В РАНДОМЕ", get_font(38), fill="#FF9900")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Собрал крафт на 25 тонн чистого чугуна...", get_font(28))

    mam = get_asset("mammoth.png")
    if mam:
        m = Image.open(mam).convert("RGBA").resize((380, 280))
        img.paste(m, (260, 210), m)

    draw_text_with_outline(draw, (60, 560), "Пока доехал до центра карты со скоростью 30 км/ч:", get_font(26), fill="#FFCC00")
    draw_text_with_outline(draw, (70, 640), "Вся союзная команда уже дружно в ангаре 💀", get_font(34), fill="#FF3333")
    draw_text_with_outline(draw, (140, 740), "«Один против шести ховеров с деструкторами. F»", get_font(26), fill="#888888")
    return img, "mammoth_tank", headline

def gen_harvester_ambush():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(22, 18, 24))
    draw = ImageDraw.Draw(img)
    headline = "НЕВИДИМЫЙ УТЮГ СО ЖНЕЦОМ В КУСТАХ"

    draw_text_with_outline(draw, (80, 40), "ТИХАЯ ОХОТА В ПУСТОШАХ", get_font(38), fill="#EC4899")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Спокойно стоишь на холме и выцеливаешь противника...", get_font(26))

    hv = get_asset("harvester.png")
    if hv:
        h = Image.open(hv).convert("RGBA").resize((380, 280))
        img.paste(h, (260, 210), h)

    draw_text_with_outline(draw, (60, 560), "Звук из кустов за твоей спиной через 2 секунды:", get_font(26), fill="#FBBF24")
    draw_text_with_outline(draw, (80, 630), "«ВЖЖЖЖЖ-ХРУСЬ-ХРУСЬ» (Рама отвалилась) 💀", get_font(32), fill="#EF4444")
    draw_text_with_outline(draw, (180, 730), "«Доброго вечора, вы приняты в ангар»", get_font(28), fill="#94A3B8")
    return img, "harvester_ambush", headline

def gen_clown_progression():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(20, 20, 26))
    draw = ImageDraw.Draw(img)
    headline = "ЭВОЛЮЦИЯ ИГРОКА В CROSSOUT: 4 СТАДИИ КЛОУНАДЫ"

    draw_text_with_outline(draw, (70, 35), "СТАДИИ СБОРКИ КРАФТА В CROSSOUT", get_font(36), fill="#F59E0B")
    draw.line([(40, 85), (860, 85)], fill="#555555", width=3)

    steps = [
        ("1. «Сейчас соберу непобедимую имбу сам»", "#38BDF8"),
        ("2. «Ладно, поставлю Газген, энергии не хватает»", "#FBBF24"),
        ("3. «Перегруз +8000 кг? Колеса и так поедут»", "#FB7185"),
        ("4. «Сдетонировал на спавне, команда виновата»", "#EF4444")
    ]

    y = 130
    for text, color in steps:
        draw.rectangle([(50, y), (850, y + 100)], fill=(28, 30, 42), outline=color, width=2)
        draw_text_with_outline(draw, (80, y + 30), text, get_font(28), fill=color)
        y += 135

    draw_text_with_outline(draw, (160, 720), "«И так каждый божий день в рандоме»", get_font(30), fill="#94A3B8")
    return img, "clown_progression", headline

def gen_doge_comparison():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 22, 28))
    draw = ImageDraw.Draw(img)
    headline = "КРАФТ В ТЕСТ-ДРАЙВЕ VS КРАФТ В РЕАЛЬНОМ БОЮ"

    draw_text_with_outline(draw, (60, 40), "КРАФТ В ГАРАЖЕ  VS  КРАФТ В БОЮ", get_font(36), fill="#FBBF24")
    draw.line([(40, 90), (860, 90)], fill="#555555", width=3)

    draw.rectangle([(40, 130), (430, 680)], fill=(24, 30, 40), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (60, 150), "В ТЕСТ-ДРАЙВЕ:", get_font(30), fill="#38BDF8")
    draw_text_with_outline(draw, (60, 220), "• Скорость 120 км/ч", get_font(24))
    draw_text_with_outline(draw, (60, 270), "• Дроны разваливают ботов", get_font(24))
    draw_text_with_outline(draw, (60, 320), "• Броня держит всё", get_font(24))
    draw_text_with_outline(draw, (60, 370), "• Чувствуешь себя богом", get_font(24), fill="#4ADE80")

    draw.rectangle([(470, 130), (860, 680)], fill=(32, 24, 28), outline="#EF4444", width=2)
    draw_text_with_outline(draw, (490, 150), "В ПЕРВОМ БОЮ:", get_font(30), fill="#EF4444")
    draw_text_with_outline(draw, (490, 220), "• Застрял в союзнике", get_font(24))
    draw_text_with_outline(draw, (490, 270), "• Вереск прилетел в крышу", get_font(24))
    draw_text_with_outline(draw, (490, 320), "• Оторвало оба колеса", get_font(24))
    draw_text_with_outline(draw, (490, 370), "• Ангар через 8 секунд", get_font(24), fill="#F87171")

    draw_text_with_outline(draw, (140, 740), "«Классика жанра, которой нет конца»", get_font(32), fill="#E2E8F0")
    return img, "doge_comparison", headline

def gen_hover_physics():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(16, 22, 30))
    draw = ImageDraw.Draw(img)
    headline = "ФИЗИКА ХОВЕРОВ В CROSSOUT: ПОЛЕТ В КОСМОС"

    draw_text_with_outline(draw, (90, 40), "ФИЗИКА ХОВЕРОВ В 2026 ГОДУ", get_font(38), fill="#00E5FF")
    draw.line([(50, 100), (850, 100)], fill="#444444", width=3)
    draw_text_with_outline(draw, (60, 140), "Паришь над землей, чувствуешь превосходство...", get_font(26))

    hov = get_asset("hover.png")
    if hov:
        h = Image.open(hov).convert("RGBA").resize((380, 280))
        img.paste(h, (260, 210), h)

    draw_text_with_outline(draw, (60, 560), "Наехал левым ховером на маленький камешек:", get_font(26), fill="#FFD600")
    draw_text_with_outline(draw, (80, 640), "Сальто назад 720° и приземление на Газген 💀", get_font(32), fill="#FF1744")
    draw_text_with_outline(draw, (180, 740), "«Гравитация Пустошей беспощадна»", get_font(28), fill="#80D8FF")
    return img, "hover_physics", headline

ALL_GENERATORS = [
    ("rw_1", gen_rw_crossover_1),
    ("rw_2", gen_rw_crossover_2),
    ("autobuild", gen_autobuild),
    ("gasgen", gen_gasgen_blast),
    ("ptur", gen_ptur_sniper),
    ("scorpion", gen_scorpion_relic),
    ("mammoth", gen_mammoth_tank),
    ("harvester", gen_harvester_ambush),
    ("clown", gen_clown_progression),
    ("doge", gen_doge_comparison),
    ("hover", gen_hover_physics),
]

def generate_crossout_meme(theme="", allow_repeat=False, recipient="yarik"):
    theme_lower = (theme or "").lower()

    # If repeat is specifically requested, return the last sent meme if available
    if allow_repeat:
        last = get_last_sent_meme(sent_to=recipient) or get_last_sent_meme()
        if last and os.path.exists(last["file_path"]):
            print(f"[MEME] Repeat allowed and requested. Returning last meme: {last['file_path']}")
            return last["file_path"]

    # Select candidates matching the theme
    candidates = []
    if any(w in theme_lower for w in ["рэин", "рейн", "rain", "слизн", "скэв", "scav", "искусник", "копье", "ворлд", "rw"]):
        candidates = [gen_rw_crossover_1, gen_rw_crossover_2]
    elif "автосборк" in theme_lower:
        candidates = [gen_autobuild]
    elif any(w in theme_lower for w in ["газген", "взрыв", "детонац"]):
        candidates = [gen_gasgen_blast]
    elif any(w in theme_lower for w in ["птур", "ракета"]):
        candidates = [gen_ptur_sniper]
    elif any(w in theme_lower for w in ["скорп", "реликт"]):
        candidates = [gen_scorpion_relic]
    elif any(w in theme_lower for w in ["мамонт", "чугун", "тяж"]):
        candidates = [gen_mammoth_tank]
    elif any(w in theme_lower for w in ["жнец", "пилы", "комбайн", "инвиз"]):
        candidates = [gen_harvester_ambush]
    elif any(w in theme_lower for w in ["ховер", "полет"]):
        candidates = [gen_hover_physics]
    elif any(w in theme_lower for w in ["клоун", "стадии"]):
        candidates = [gen_clown_progression]
    elif any(w in theme_lower for w in ["доге", "дог", "сравнен"]):
        candidates = [gen_doge_comparison]

    # Combine with full generator pool shuffled
    all_funcs = [func for _, func in ALL_GENERATORS]
    random.shuffle(all_funcs)
    candidate_queue = candidates + [f for f in all_funcs if f not in candidates]

    chosen_img = None
    chosen_tpl = None
    chosen_hl = None
    chosen_hash = None

    for gen_func in candidate_queue:
        img, tpl_name, headline = gen_func()
        h = hashlib.sha256(headline.encode("utf-8") + img.tobytes()).hexdigest()

        # Check if already sent!
        if not allow_repeat and is_meme_already_sent(meme_hash=h, headline=headline):
            print(f"[MEME FILTER] Skipped repeated meme '{headline}' (hash={h[:8]})")
            continue

        chosen_img = img
        chosen_tpl = tpl_name
        chosen_hl = headline
        chosen_hash = h
        break

    # If all existing templates were somehow exhausted, create a uniquely salted variation
    if not chosen_img:
        gen_func = random.choice(all_funcs)
        chosen_img, chosen_tpl, chosen_hl = gen_func()
        # Add dynamic unique salt timestamp watermark to guarantee 100% uniqueness
        salt_text = f"№ {int(time.time() * 1000) % 100000}"
        draw = ImageDraw.Draw(chosen_img)
        draw.text((800, 920), salt_text, fill=(80, 80, 80), font=get_font(16))
        chosen_hl = f"{chosen_hl} ({salt_text})"
        chosen_hash = hashlib.sha256(chosen_hl.encode("utf-8") + chosen_img.tobytes()).hexdigest()

    # Save to media and saved_memes
    out_name = f"meme_{int(time.time())}_{random.randint(1000, 9999)}.png"
    out_path = os.path.join(MEDIA_DIR, out_name)
    chosen_img.save(out_path, "PNG")

    if os.path.exists(SAVED_MEMES_DIR):
        try:
            saved_copy = os.path.join(SAVED_MEMES_DIR, out_name)
            shutil.copy2(out_path, saved_copy)
            try:
                from gdrive import upload_file_to_drive
                upload_file_to_drive(saved_copy)
            except Exception:
                pass
        except Exception:
            pass

    # Record in database so it can NEVER be repeated!
    record_sent_meme(chosen_hash, chosen_tpl, chosen_hl, out_path, sent_to=recipient)
    print(f"[MEME RECORDED] Successfully registered new unique meme '{chosen_hl}' (hash={chosen_hash[:8]}) for {recipient}")

    return out_path
